"""
Inspector Tool for QGIS Geemap

This module provides an Inspector tool similar to the Earth Engine
Code Editor Inspector, allowing users to click on the map to inspect
Earth Engine layer values at that location.
"""

import json
from typing import Any, Dict, List, Optional

from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QGroupBox,
    QTreeWidget,
    QTreeWidgetItem,
    QProgressBar,
    QTabWidget,
    QHeaderView,
    QSplitter,
)
from qgis.PyQt.QtGui import QFont, QCursor, QColor
from qgis.gui import QgsMapTool, QgsMapCanvas
from qgis.core import (
    QgsProject,
    QgsPointXY,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
)

try:
    import ee
except ImportError:
    ee = None


class InspectorWorker(QThread):
    """Worker thread for fetching Earth Engine data at a point."""

    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, ee_layers: Dict[str, tuple], point: tuple, scale: float = 30):
        """Initialize the worker.

        Args:
            ee_layers: Dictionary of layer name -> (ee_object, vis_params)
            point: (lon, lat) tuple
            scale: Scale in meters for sampling
        """
        super().__init__()
        self.ee_layers = ee_layers
        self.point = point
        self.scale = scale

    def run(self):
        """Fetch data for all layers at the point."""
        if ee is None:
            self.error.emit("Earth Engine API not available")
            return

        results = {
            "point": {"lon": self.point[0], "lat": self.point[1]},
            "layers": {},
        }

        lon, lat = self.point
        point_geom = ee.Geometry.Point([lon, lat])

        for name, (ee_object, vis_params) in self.ee_layers.items():
            try:
                self.progress.emit(f"Inspecting: {name}")

                if isinstance(ee_object, ee.Image):
                    # Sample the image at the point
                    # Use reduceRegion instead of sample for more reliable point sampling
                    point_buffer = point_geom.buffer(self.scale / 2)

                    # Try to get band names to check if this is a valid data image
                    try:
                        band_names = ee_object.bandNames().getInfo()
                    except Exception:
                        band_names = []

                    if not band_names:
                        # No bands - likely a styled/visualization image
                        results["layers"][name] = {
                            "type": "Image",
                            "values": {"note": "Visualization layer (no band data)"},
                        }
                        continue

                    sampled = ee_object.reduceRegion(
                        reducer=ee.Reducer.first(),
                        geometry=point_buffer,
                        scale=self.scale,
                        bestEffort=True,
                        maxPixels=1,
                    ).getInfo()

                    if sampled and any(v is not None for v in sampled.values()):
                        # Filter out None values
                        filtered_values = {
                            k: v for k, v in sampled.items() if v is not None
                        }
                        if filtered_values:
                            results["layers"][name] = {
                                "type": "Image",
                                "values": filtered_values,
                            }
                        else:
                            results["layers"][name] = {
                                "type": "Image",
                                "values": {"note": "No data at this location"},
                            }
                    else:
                        results["layers"][name] = {
                            "type": "Image",
                            "values": {"note": "No data at this location"},
                        }

                elif isinstance(ee_object, ee.ImageCollection):
                    # Get the mosaic and sample it
                    image = ee_object.mosaic()
                    point_buffer = point_geom.buffer(self.scale / 2)
                    sampled = image.reduceRegion(
                        reducer=ee.Reducer.first(),
                        geometry=point_buffer,
                        scale=self.scale,
                        bestEffort=True,
                        maxPixels=1,
                    ).getInfo()

                    if sampled and any(v is not None for v in sampled.values()):
                        # Filter out None values
                        filtered_values = {
                            k: v for k, v in sampled.items() if v is not None
                        }
                        if filtered_values:
                            results["layers"][name] = {
                                "type": "ImageCollection",
                                "values": filtered_values,
                            }
                        else:
                            results["layers"][name] = {
                                "type": "ImageCollection",
                                "values": {"note": "No data at this location"},
                            }
                    else:
                        results["layers"][name] = {
                            "type": "ImageCollection",
                            "values": {"note": "No data at this location"},
                        }

                elif isinstance(ee_object, ee.FeatureCollection):
                    # Filter features that contain the point
                    filtered = ee_object.filterBounds(point_geom)
                    filtered = filtered.map(
                        lambda f: ee.Feature(None, f.toDictionary(f.propertyNames()))
                    )
                    count = filtered.size().getInfo()

                    if count > 0:
                        features = filtered.limit(10).getInfo()
                        feature_props = []
                        for f in features.get("features", []):
                            feature_props.append(f.get("properties", {}))
                        results["layers"][name] = {
                            "type": "FeatureCollection",
                            "count": count,
                            "features": feature_props,
                        }
                    else:
                        results["layers"][name] = {
                            "type": "FeatureCollection",
                            "count": 0,
                            "features": [],
                        }

            except Exception as e:
                results["layers"][name] = {
                    "type": "Error",
                    "error": str(e),
                }

        self.finished.emit(results)


class InspectorMapTool(QgsMapTool):
    """Map tool for inspecting Earth Engine layers."""

    inspected = pyqtSignal(float, float)  # lon, lat

    def __init__(self, canvas: QgsMapCanvas, inspector_dock: "InspectorDockWidget"):
        """Initialize the Inspector map tool.

        Args:
            canvas: QGIS map canvas.
            inspector_dock: Inspector dock widget to display results.
        """
        super().__init__(canvas)
        self.inspector_dock = inspector_dock
        self.setCursor(QCursor(Qt.CrossCursor))

    def canvasReleaseEvent(self, event):
        """Handle mouse click on the map."""
        # Get the click point in map coordinates
        point = self.toMapCoordinates(event.pos())

        # Transform to EPSG:4326
        project = QgsProject.instance()
        src_crs = self.canvas().mapSettings().destinationCrs()
        dst_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        transform = QgsCoordinateTransform(src_crs, dst_crs, project)

        point_4326 = transform.transform(point)
        lon, lat = point_4326.x(), point_4326.y()

        # Emit signal and trigger inspection
        self.inspected.emit(lon, lat)
        self.inspector_dock.inspect_point(lon, lat)


class InspectorDockWidget(QDockWidget):
    """Dock widget for displaying inspection results."""

    def __init__(self, iface, parent=None):
        """Initialize the Inspector dock widget.

        Args:
            iface: QGIS interface instance.
            parent: Parent widget.
        """
        super().__init__("Inspector", parent)
        self.iface = iface
        self._worker = None

        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._setup_ui()

    def _setup_ui(self):
        """Set up the dock widget UI."""
        main_widget = QWidget()
        self.setWidget(main_widget)

        layout = QVBoxLayout(main_widget)
        layout.setSpacing(10)

        # Header
        header_label = QLabel("Earth Engine Inspector")
        header_font = QFont()
        header_font.setPointSize(12)
        header_font.setBold(True)
        header_label.setFont(header_font)
        header_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(header_label)

        # Instructions
        instructions = QLabel("Click on the map to inspect Earth Engine layers")
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: gray;")
        layout.addWidget(instructions)

        # Location info
        location_group = QGroupBox("Location")
        location_layout = QHBoxLayout(location_group)

        self.lon_label = QLabel("Lon: --")
        self.lat_label = QLabel("Lat: --")
        location_layout.addWidget(self.lon_label)
        location_layout.addWidget(self.lat_label)

        layout.addWidget(location_group)

        # Results tree
        results_group = QGroupBox("Layer Values")
        results_layout = QVBoxLayout(results_group)

        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderLabels(["Property", "Value"])
        self.results_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.results_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.results_tree.setAlternatingRowColors(True)
        results_layout.addWidget(self.results_tree)

        layout.addWidget(results_group)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Ready - Click on map to inspect")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.status_label)

        # Clear button
        clear_btn = QPushButton("Clear Results")
        clear_btn.clicked.connect(self._clear_results)
        layout.addWidget(clear_btn)

    def _get_ee_layers(self):
        """Get the EE layers from the active Map instance."""
        try:
            from ..core.map_registry import get_ee_layers

            return get_ee_layers()
        except Exception:
            return {}

    def inspect_point(self, lon: float, lat: float):
        """Inspect Earth Engine layers at the given point.

        Args:
            lon: Longitude.
            lat: Latitude.
        """
        # Update location display
        self.lon_label.setText(f"Lon: {lon:.6f}")
        self.lat_label.setText(f"Lat: {lat:.6f}")

        # Get the EE layers from the active Map instance
        ee_layers = self._get_ee_layers()
        if not ee_layers:
            self.status_label.setText(
                "No Earth Engine layers to inspect. Add layers using geemap.Map()"
            )
            self.status_label.setStyleSheet("color: orange; font-size: 10px;")
            return

        # Stop any running worker
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait()

        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.status_label.setText("Inspecting...")
        self.status_label.setStyleSheet("color: blue; font-size: 10px;")
        self.results_tree.clear()

        # Calculate scale based on current map zoom
        canvas = self.iface.mapCanvas()
        scale = canvas.scale()
        # Convert map scale to approximate meters per pixel
        ee_scale = max(10, min(1000, scale / 3000))

        # Start worker with the EE layers
        self._worker = InspectorWorker(ee_layers, (lon, lat), ee_scale)
        self._worker.finished.connect(self._on_inspection_finished)
        self._worker.error.connect(self._on_inspection_error)
        self._worker.progress.connect(self._on_inspection_progress)
        self._worker.start()

    def _on_inspection_progress(self, message: str):
        """Handle progress updates."""
        self.status_label.setText(message)

    def _on_inspection_finished(self, results: dict):
        """Handle inspection completion."""
        self.progress_bar.setVisible(False)
        self.results_tree.clear()

        layers = results.get("layers", {})

        if not layers:
            self.status_label.setText("No layer data found at this location")
            self.status_label.setStyleSheet("color: orange; font-size: 10px;")
            return

        for layer_name, layer_data in layers.items():
            layer_item = QTreeWidgetItem([layer_name, ""])
            layer_item.setExpanded(True)

            layer_type = layer_data.get("type", "Unknown")
            type_item = QTreeWidgetItem(["Type", layer_type])
            layer_item.addChild(type_item)

            if layer_type == "Error":
                error_item = QTreeWidgetItem(["Error", layer_data.get("error", "")])
                error_item.setForeground(1, QColor("red"))
                layer_item.addChild(error_item)

            elif layer_type in ("Image", "ImageCollection"):
                values = layer_data.get("values", {})
                for key, value in values.items():
                    if isinstance(value, float):
                        value_str = f"{value:.6f}"
                    elif isinstance(value, (list, dict)):
                        value_str = json.dumps(value, indent=2)
                    else:
                        value_str = str(value)
                    value_item = QTreeWidgetItem([str(key), value_str])
                    layer_item.addChild(value_item)

            elif layer_type == "FeatureCollection":
                count = layer_data.get("count", 0)
                count_item = QTreeWidgetItem(["Features Found", str(count)])
                layer_item.addChild(count_item)

                features = layer_data.get("features", [])
                for i, feat_props in enumerate(features[:5]):  # Show max 5 features
                    feat_item = QTreeWidgetItem([f"Feature {i + 1}", ""])
                    feat_item.setExpanded(False)
                    for key, value in feat_props.items():
                        if isinstance(value, float):
                            value_str = f"{value:.6f}"
                        elif isinstance(value, (list, dict)):
                            value_str = json.dumps(value)
                        else:
                            value_str = str(value) if value is not None else ""
                        prop_item = QTreeWidgetItem([str(key), value_str])
                        feat_item.addChild(prop_item)
                    layer_item.addChild(feat_item)

            self.results_tree.addTopLevelItem(layer_item)

        # Auto-expand all items for better visibility
        self.results_tree.expandAll()

        self.status_label.setText(f"Inspected {len(layers)} layer(s)")
        self.status_label.setStyleSheet("color: green; font-size: 10px;")

    def _on_inspection_error(self, error: str):
        """Handle inspection error."""
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Error: {error}")
        self.status_label.setStyleSheet("color: red; font-size: 10px;")

    def _clear_results(self):
        """Clear the results tree."""
        self.results_tree.clear()
        self.lon_label.setText("Lon: --")
        self.lat_label.setText("Lat: --")
        self.status_label.setText("Ready - Click on map to inspect")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")

    def closeEvent(self, event):
        """Handle dock widget close event."""
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait()
        event.accept()
