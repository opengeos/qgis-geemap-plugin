"""
Export Dock Widget for QGIS Geemap

This module provides a dockable panel for exporting Earth Engine images
to local files, supporting various export options including
bounding box and vector layer extent.
"""

import os
from typing import Any, Dict, List, Optional

from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextEdit,
    QGroupBox,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QFormLayout,
    QMessageBox,
    QFileDialog,
    QProgressBar,
    QRadioButton,
    QButtonGroup,
    QScrollArea,
)
from qgis.PyQt.QtGui import QFont
from qgis.core import (
    QgsProject,
    QgsMapLayer,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsRectangle,
)
from qgis.gui import QgsMapLayerComboBox

try:
    import ee
except ImportError:
    ee = None


class ExportWorker(QThread):
    """Worker thread for exporting Earth Engine images."""

    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    progress = pyqtSignal(int, str)

    def __init__(
        self,
        ee_image: Any,
        region: Any,
        filename: str,
        scale: float = 30,
        crs: str = "EPSG:4326",
        file_format: str = "GeoTIFF",
    ):
        """Initialize the export worker.

        Args:
            ee_image: Earth Engine Image to export.
            region: Earth Engine Geometry for the export region.
            filename: Output filename.
            scale: Export scale in meters.
            crs: Coordinate reference system.
            file_format: Output file format.
        """
        super().__init__()
        self.ee_image = ee_image
        self.region = region
        self.filename = filename
        self.scale = scale
        self.crs = crs
        self.file_format = file_format

    def run(self):
        """Execute the export."""
        try:
            self.progress.emit(10, "Preparing export...")

            # Get the URL for downloading
            if self.file_format == "GeoTIFF":
                url = self.ee_image.getDownloadURL(
                    {
                        "region": self.region,
                        "scale": self.scale,
                        "crs": self.crs,
                        "format": "GEO_TIFF",
                    }
                )
            else:
                url = self.ee_image.getDownloadURL(
                    {
                        "region": self.region,
                        "scale": self.scale,
                        "crs": self.crs,
                        "format": "NPY",
                    }
                )

            self.progress.emit(30, "Downloading image...")

            # Download the file
            import urllib.request

            def reporthook(block_num, block_size, total_size):
                if total_size > 0:
                    downloaded = block_num * block_size
                    percent = min(int((downloaded / total_size) * 60) + 30, 90)
                    self.progress.emit(percent, "Downloading...")

            urllib.request.urlretrieve(url, self.filename, reporthook)

            self.progress.emit(100, "Export complete!")
            self.finished.emit(self.filename)

        except Exception as e:
            self.error.emit(str(e))


class ExportDockWidget(QDockWidget):
    """Dockable panel for exporting Earth Engine images."""

    def __init__(self, iface, parent=None):
        """Initialize the Export dock widget.

        Args:
            iface: QGIS interface instance.
            parent: Parent widget.
        """
        super().__init__("Export EE Image", parent)
        self.iface = iface
        self._worker = None

        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._setup_ui()
        self._refresh_ee_layers()

    def _get_ee_layers(self):
        """Get the EE layers from the active Map instance."""
        try:
            from ..core.map_registry import get_ee_layers

            return get_ee_layers()
        except Exception:
            return {}

    def _setup_ui(self):
        """Set up the dock widget UI."""
        # Create scroll area for the content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(10)

        # Header
        header_label = QLabel("Export Earth Engine Image")
        header_font = QFont()
        header_font.setPointSize(11)
        header_font.setBold(True)
        header_label.setFont(header_font)
        header_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(header_label)

        # Image selection
        image_group = QGroupBox("Image to Export")
        image_layout = QFormLayout(image_group)

        # EE Layer combo
        layer_layout = QHBoxLayout()
        self.ee_layer_combo = QComboBox()
        layer_layout.addWidget(self.ee_layer_combo)

        refresh_btn = QPushButton("↻")
        refresh_btn.setMaximumWidth(30)
        refresh_btn.setToolTip("Refresh EE layers")
        refresh_btn.clicked.connect(self._refresh_ee_layers)
        layer_layout.addWidget(refresh_btn)

        image_layout.addRow("EE Layer:", layer_layout)

        # Custom asset ID option
        self.custom_asset_check = QCheckBox("Use custom asset ID")
        self.custom_asset_check.stateChanged.connect(self._toggle_custom_asset)
        image_layout.addRow("", self.custom_asset_check)

        self.custom_asset_input = QLineEdit()
        self.custom_asset_input.setPlaceholderText("e.g., USGS/SRTMGL1_003")
        self.custom_asset_input.setEnabled(False)
        image_layout.addRow("Asset ID:", self.custom_asset_input)

        layout.addWidget(image_group)

        # Region selection
        region_group = QGroupBox("Export Region")
        region_layout = QVBoxLayout(region_group)

        # Region type selection
        self.region_type_group = QButtonGroup()

        self.use_canvas_radio = QRadioButton("Current map canvas extent")
        self.use_canvas_radio.setChecked(True)
        self.region_type_group.addButton(self.use_canvas_radio)
        region_layout.addWidget(self.use_canvas_radio)

        self.use_layer_radio = QRadioButton("Vector layer extent")
        self.region_type_group.addButton(self.use_layer_radio)
        region_layout.addWidget(self.use_layer_radio)

        # Layer selection for extent
        layer_extent_layout = QHBoxLayout()
        layer_extent_layout.addSpacing(20)
        self.extent_layer_combo = QgsMapLayerComboBox()
        self.extent_layer_combo.setFilters(
            self.extent_layer_combo.filters() | 1  # Vector layers
        )
        self.extent_layer_combo.setEnabled(False)
        layer_extent_layout.addWidget(self.extent_layer_combo)
        region_layout.addLayout(layer_extent_layout)

        self.use_custom_radio = QRadioButton("Custom bounding box")
        self.region_type_group.addButton(self.use_custom_radio)
        region_layout.addWidget(self.use_custom_radio)

        # Custom bbox inputs
        bbox_layout = QFormLayout()
        bbox_layout.setContentsMargins(20, 0, 0, 0)

        self.min_lon_spin = QDoubleSpinBox()
        self.min_lon_spin.setRange(-180, 180)
        self.min_lon_spin.setDecimals(6)
        self.min_lon_spin.setEnabled(False)
        bbox_layout.addRow("Min Lon:", self.min_lon_spin)

        self.min_lat_spin = QDoubleSpinBox()
        self.min_lat_spin.setRange(-90, 90)
        self.min_lat_spin.setDecimals(6)
        self.min_lat_spin.setEnabled(False)
        bbox_layout.addRow("Min Lat:", self.min_lat_spin)

        self.max_lon_spin = QDoubleSpinBox()
        self.max_lon_spin.setRange(-180, 180)
        self.max_lon_spin.setDecimals(6)
        self.max_lon_spin.setEnabled(False)
        bbox_layout.addRow("Max Lon:", self.max_lon_spin)

        self.max_lat_spin = QDoubleSpinBox()
        self.max_lat_spin.setRange(-90, 90)
        self.max_lat_spin.setDecimals(6)
        self.max_lat_spin.setEnabled(False)
        bbox_layout.addRow("Max Lat:", self.max_lat_spin)

        region_layout.addLayout(bbox_layout)

        # Connect radio button signals
        self.use_canvas_radio.toggled.connect(self._update_region_inputs)
        self.use_layer_radio.toggled.connect(self._update_region_inputs)
        self.use_custom_radio.toggled.connect(self._update_region_inputs)

        # Get from canvas button
        get_canvas_btn = QPushButton("Get Current Canvas Extent")
        get_canvas_btn.clicked.connect(self._get_canvas_extent)
        region_layout.addWidget(get_canvas_btn)

        layout.addWidget(region_group)

        # Export options
        options_group = QGroupBox("Export Options")
        options_layout = QFormLayout(options_group)

        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(1, 10000)
        self.scale_spin.setValue(30)
        self.scale_spin.setSuffix(" m")
        options_layout.addRow("Scale:", self.scale_spin)

        self.crs_combo = QComboBox()
        self.crs_combo.addItems(
            [
                "EPSG:4326",
                "EPSG:3857",
                "EPSG:32610",
                "EPSG:32611",
                "EPSG:32618",
                "EPSG:32619",
            ]
        )
        options_layout.addRow("CRS:", self.crs_combo)

        self.format_combo = QComboBox()
        self.format_combo.addItems(["GeoTIFF"])
        options_layout.addRow("Format:", self.format_combo)

        layout.addWidget(options_group)

        # Output file
        output_group = QGroupBox("Output")
        output_layout = QHBoxLayout(output_group)

        self.output_input = QLineEdit()
        self.output_input.setPlaceholderText("Select output file...")
        output_layout.addWidget(self.output_input)

        browse_btn = QPushButton("...")
        browse_btn.setMaximumWidth(30)
        browse_btn.clicked.connect(self._browse_output)
        output_layout.addWidget(browse_btn)

        layout.addWidget(output_group)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.status_label)

        # Export button
        self.export_btn = QPushButton("Export Image")
        self.export_btn.clicked.connect(self._start_export)
        layout.addWidget(self.export_btn)

        # Note
        note_label = QLabel(
            "<small><b>Note:</b> Large exports may fail. For large areas, "
            "use EE Tasks to export to Drive.</small>"
        )
        note_label.setWordWrap(True)
        note_label.setStyleSheet("color: gray;")
        layout.addWidget(note_label)

        layout.addStretch()

        scroll_area.setWidget(main_widget)
        self.setWidget(scroll_area)

    def _refresh_ee_layers(self):
        """Refresh the EE layer combo box."""
        self.ee_layer_combo.clear()
        self.ee_layer_combo.addItem("-- Select EE Layer --", None)

        ee_layers = self._get_ee_layers()
        if ee_layers:
            for name, (ee_obj, vis_params) in ee_layers.items():
                if ee is not None and isinstance(
                    ee_obj, (ee.Image, ee.ImageCollection)
                ):
                    self.ee_layer_combo.addItem(name, name)

        if self.ee_layer_combo.count() == 1:
            self.status_label.setText("No EE Image layers found. Add layers first.")
            self.status_label.setStyleSheet("color: orange; font-size: 10px;")
        else:
            self.status_label.setText(
                f"Found {self.ee_layer_combo.count() - 1} EE layer(s)"
            )
            self.status_label.setStyleSheet("color: green; font-size: 10px;")

    def _toggle_custom_asset(self, state):
        """Toggle custom asset ID input."""
        self.custom_asset_input.setEnabled(state == Qt.Checked)
        self.ee_layer_combo.setEnabled(state != Qt.Checked)

    def _update_region_inputs(self):
        """Update region input states based on selection."""
        self.extent_layer_combo.setEnabled(self.use_layer_radio.isChecked())

        custom_enabled = self.use_custom_radio.isChecked()
        self.min_lon_spin.setEnabled(custom_enabled)
        self.min_lat_spin.setEnabled(custom_enabled)
        self.max_lon_spin.setEnabled(custom_enabled)
        self.max_lat_spin.setEnabled(custom_enabled)

    def _get_canvas_extent(self):
        """Get the current canvas extent and fill in the bbox fields."""
        canvas = self.iface.mapCanvas()
        extent = canvas.extent()

        # Transform to EPSG:4326
        project = QgsProject.instance()
        src_crs = canvas.mapSettings().destinationCrs()
        dst_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        transform = QgsCoordinateTransform(src_crs, dst_crs, project)
        extent_4326 = transform.transformBoundingBox(extent)

        self.min_lon_spin.setValue(extent_4326.xMinimum())
        self.min_lat_spin.setValue(extent_4326.yMinimum())
        self.max_lon_spin.setValue(extent_4326.xMaximum())
        self.max_lat_spin.setValue(extent_4326.yMaximum())

        self.use_custom_radio.setChecked(True)

    def _browse_output(self):
        """Browse for output file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Export As",
            "",
            "GeoTIFF (*.tif *.tiff);;All Files (*)",
        )
        if file_path:
            if not file_path.lower().endswith((".tif", ".tiff")):
                file_path += ".tif"
            self.output_input.setText(file_path)

    def _get_region(self):
        """Get the export region as an Earth Engine geometry."""
        if ee is None:
            raise ValueError("Earth Engine API not available")

        if self.use_canvas_radio.isChecked():
            # Get canvas extent
            canvas = self.iface.mapCanvas()
            extent = canvas.extent()

            # Transform to EPSG:4326
            project = QgsProject.instance()
            src_crs = canvas.mapSettings().destinationCrs()
            dst_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            transform = QgsCoordinateTransform(src_crs, dst_crs, project)
            extent_4326 = transform.transformBoundingBox(extent)

            return ee.Geometry.Rectangle(
                [
                    extent_4326.xMinimum(),
                    extent_4326.yMinimum(),
                    extent_4326.xMaximum(),
                    extent_4326.yMaximum(),
                ]
            )

        elif self.use_layer_radio.isChecked():
            # Get layer extent
            layer = self.extent_layer_combo.currentLayer()
            if not layer:
                raise ValueError("Please select a vector layer for the extent")

            extent = layer.extent()

            # Transform to EPSG:4326
            project = QgsProject.instance()
            src_crs = layer.crs()
            dst_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            transform = QgsCoordinateTransform(src_crs, dst_crs, project)
            extent_4326 = transform.transformBoundingBox(extent)

            return ee.Geometry.Rectangle(
                [
                    extent_4326.xMinimum(),
                    extent_4326.yMinimum(),
                    extent_4326.xMaximum(),
                    extent_4326.yMaximum(),
                ]
            )

        else:
            # Custom bbox
            return ee.Geometry.Rectangle(
                [
                    self.min_lon_spin.value(),
                    self.min_lat_spin.value(),
                    self.max_lon_spin.value(),
                    self.max_lat_spin.value(),
                ]
            )

    def _get_image(self):
        """Get the Earth Engine image to export."""
        if ee is None:
            raise ValueError("Earth Engine API not available")

        if self.custom_asset_check.isChecked():
            asset_id = self.custom_asset_input.text().strip()
            if not asset_id:
                raise ValueError("Please enter an asset ID")
            return ee.Image(asset_id)

        layer_name = self.ee_layer_combo.currentData()
        if not layer_name:
            raise ValueError("Please select an EE layer to export")

        ee_layers = self._get_ee_layers()
        if layer_name not in ee_layers:
            raise ValueError(f"Layer '{layer_name}' not found")

        ee_obj, vis_params = ee_layers[layer_name]

        if isinstance(ee_obj, ee.ImageCollection):
            return ee_obj.mosaic()
        elif isinstance(ee_obj, ee.Image):
            return ee_obj
        else:
            raise ValueError("Selected layer is not an Image or ImageCollection")

    def _start_export(self):
        """Start the export process."""
        try:
            # Validate inputs
            output_file = self.output_input.text().strip()
            if not output_file:
                QMessageBox.warning(self, "Warning", "Please specify an output file")
                return

            # Get image and region
            image = self._get_image()
            region = self._get_region()

            # Disable UI
            self.export_btn.setEnabled(False)
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.status_label.setText("Exporting...")
            self.status_label.setStyleSheet("color: blue; font-size: 10px;")

            # Start worker
            self._worker = ExportWorker(
                ee_image=image,
                region=region,
                filename=output_file,
                scale=self.scale_spin.value(),
                crs=self.crs_combo.currentText(),
                file_format=self.format_combo.currentText(),
            )
            self._worker.finished.connect(self._on_export_finished)
            self._worker.error.connect(self._on_export_error)
            self._worker.progress.connect(self._on_export_progress)
            self._worker.start()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Export failed:\n{str(e)}")

    def _on_export_progress(self, percent: int, message: str):
        """Handle export progress."""
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)

    def _on_export_finished(self, filename: str):
        """Handle export completion."""
        self.progress_bar.setVisible(False)
        self.export_btn.setEnabled(True)
        self.status_label.setText("Export complete!")
        self.status_label.setStyleSheet("color: green; font-size: 10px;")

        reply = QMessageBox.information(
            self,
            "Export Complete",
            f"Image exported to:\n{filename}\n\nAdd to map?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )

        if reply == QMessageBox.Yes:
            # Add the exported image to QGIS
            layer_name = os.path.basename(filename)
            layer = QgsRasterLayer(filename, layer_name)
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)
                self.iface.messageBar().pushSuccess("Geemap", f"Added: {layer_name}")

    def _on_export_error(self, error: str):
        """Handle export error."""
        self.progress_bar.setVisible(False)
        self.export_btn.setEnabled(True)
        self.status_label.setText(f"Error: {error[:50]}...")
        self.status_label.setStyleSheet("color: red; font-size: 10px;")

        QMessageBox.critical(
            self,
            "Export Error",
            f"Export failed:\n\n{error}\n\n" "For large areas, use EE Tasks.",
        )

    def closeEvent(self, event):
        """Handle dock widget close event."""
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait()
        event.accept()
