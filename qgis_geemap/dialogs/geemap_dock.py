"""
Geemap Dock Widget

This module provides the main geemap panel for adding Earth Engine
layers and performing common operations.
"""

from qgis.PyQt.QtCore import Qt, QCoreApplication
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
    QProgressBar,
    QTabWidget,
    QPlainTextEdit,
    QSplitter,
    QApplication,
)
from qgis.PyQt.QtGui import QFont, QCursor
from qgis.core import QgsProject

try:
    import ee
except ImportError:
    ee = None


class GeemapDockWidget(QDockWidget):
    """Main geemap panel for Earth Engine operations."""

    def __init__(self, iface, parent=None):
        """Initialize the dock widget.

        Args:
            iface: QGIS interface instance.
            parent: Parent widget.
        """
        super().__init__("Geemap", parent)
        self.iface = iface
        self._map = None

        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )

        self._setup_ui()

    def _setup_ui(self):
        """Set up the dock widget UI."""
        # Main widget
        main_widget = QWidget()
        self.setWidget(main_widget)

        # Main layout
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(10)

        # Header
        header_label = QLabel("Geemap for QGIS")
        header_font = QFont()
        header_font.setPointSize(12)
        header_font.setBold(True)
        header_label.setFont(header_font)
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header_label)

        # Tab widget
        tab_widget = QTabWidget()
        layout.addWidget(tab_widget)

        # Add Layers tab
        layers_tab = self._create_layers_tab()
        tab_widget.addTab(layers_tab, "Add Layers")

        # Code Console tab
        console_tab = self._create_console_tab()
        tab_widget.addTab(console_tab, "Code")

        # Basemaps tab
        basemaps_tab = self._create_basemaps_tab()
        tab_widget.addTab(basemaps_tab, "Basemaps")

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.status_label)

    def _create_layers_tab(self):
        """Create the add layers tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Earth Engine Image section
        image_group = QGroupBox("Earth Engine Image")
        image_layout = QFormLayout(image_group)

        self.image_id_input = QLineEdit()
        self.image_id_input.setPlaceholderText("e.g., USGS/SRTMGL1_003")
        image_layout.addRow("Asset ID:", self.image_id_input)

        # Visualization parameters
        self.vis_min_spin = QDoubleSpinBox()
        self.vis_min_spin.setRange(-1e10, 1e10)
        self.vis_min_spin.setValue(0)
        image_layout.addRow("Min:", self.vis_min_spin)

        self.vis_max_spin = QDoubleSpinBox()
        self.vis_max_spin.setRange(-1e10, 1e10)
        self.vis_max_spin.setValue(3000)
        image_layout.addRow("Max:", self.vis_max_spin)

        self.palette_input = QLineEdit()
        self.palette_input.setPlaceholderText(
            "e.g., blue,green,red or #0000FF,#00FF00,#FF0000"
        )
        image_layout.addRow("Palette:", self.palette_input)

        self.bands_input = QLineEdit()
        self.bands_input.setPlaceholderText("e.g., B4,B3,B2 for RGB")
        image_layout.addRow("Bands:", self.bands_input)

        self.layer_name_input = QLineEdit()
        self.layer_name_input.setPlaceholderText("Layer name (optional)")
        image_layout.addRow("Name:", self.layer_name_input)

        add_image_btn = QPushButton("Add Image Layer")
        add_image_btn.clicked.connect(self._add_image_layer)
        image_layout.addRow("", add_image_btn)

        layout.addWidget(image_group)

        # Feature Collection section
        fc_group = QGroupBox("Feature Collection")
        fc_layout = QFormLayout(fc_group)

        self.fc_id_input = QLineEdit()
        self.fc_id_input.setPlaceholderText("e.g., TIGER/2018/States")
        fc_layout.addRow("Asset ID:", self.fc_id_input)

        self.fc_name_input = QLineEdit()
        self.fc_name_input.setPlaceholderText("Layer name (optional)")
        fc_layout.addRow("Name:", self.fc_name_input)

        self.fc_as_vector = QCheckBox("Load as vector layer")
        self.fc_as_vector.setChecked(False)
        fc_layout.addRow("", self.fc_as_vector)

        add_fc_btn = QPushButton("Add FeatureCollection Layer")
        add_fc_btn.clicked.connect(self._add_fc_layer)
        fc_layout.addRow("", add_fc_btn)

        layout.addWidget(fc_group)

        layout.addStretch()
        return widget

    def _create_console_tab(self):
        """Create the code console tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Instructions
        instructions = QLabel(
            "Enter Python code to execute. Use 'm' as the Map object.\n"
            "Example: m.add_layer(ee.Image('USGS/SRTMGL1_003'), {}, 'DEM')"
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: gray;")
        layout.addWidget(instructions)

        # Code input
        self.code_input = QPlainTextEdit()
        self.code_input.setPlaceholderText(
            "# Example code:\n"
            "import ee\n"
            "dem = ee.Image('USGS/SRTMGL1_003')\n"
            "vis = {'min': 0, 'max': 4000, 'palette': ['green', 'yellow', 'brown', 'white']}\n"
            "m.add_layer(dem, vis, 'SRTM DEM')"
        )
        layout.addWidget(self.code_input)

        # Buttons
        btn_layout = QHBoxLayout()

        run_btn = QPushButton("Run Code")
        run_btn.clicked.connect(self._run_code)
        btn_layout.addWidget(run_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(lambda: self.code_input.clear())
        btn_layout.addWidget(clear_btn)

        layout.addLayout(btn_layout)

        # Output
        self.code_output = QTextEdit()
        self.code_output.setReadOnly(True)
        self.code_output.setMaximumHeight(100)
        self.code_output.setPlaceholderText("Output will appear here...")
        layout.addWidget(self.code_output)

        return widget

    def _create_basemaps_tab(self):
        """Create the basemaps tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        basemap_group = QGroupBox("Add Basemap")
        basemap_layout = QFormLayout(basemap_group)

        self.basemap_combo = QComboBox()
        basemaps = [
            "OpenStreetMap",
            "Google Maps",
            "Google Satellite",
            "Google Terrain",
            "Google Satellite Hybrid",
            "CartoDB Positron",
            "CartoDB Dark Matter",
            "Esri World Imagery",
        ]
        self.basemap_combo.addItems(basemaps)
        basemap_layout.addRow("Basemap:", self.basemap_combo)

        add_basemap_btn = QPushButton("Add Basemap")
        add_basemap_btn.clicked.connect(self._add_basemap)
        basemap_layout.addRow("", add_basemap_btn)

        layout.addWidget(basemap_group)

        # Quick actions
        actions_group = QGroupBox("Quick Actions")
        actions_layout = QVBoxLayout(actions_group)

        center_btn = QPushButton("Center on Current View")
        center_btn.clicked.connect(self._center_on_view)
        actions_layout.addWidget(center_btn)

        clear_btn = QPushButton("Clear All EE Layers")
        clear_btn.clicked.connect(self._clear_ee_layers)
        actions_layout.addWidget(clear_btn)

        layout.addWidget(actions_group)

        layout.addStretch()
        return widget

    def _get_map(self):
        """Get or create the Map instance.

        Always gets the latest active map from the registry to ensure
        we're working with the correct Map instance (the one with layers).
        """
        try:
            from ..core.map_registry import get_active_map
            from ..core.qgis_map import Map

            # Always get the latest active map from registry
            active_map = get_active_map()
            if active_map is not None:
                self._map = active_map
            elif self._map is None:
                # Create a new one only if none exists anywhere
                self._map = Map()
            return self._map
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to create Map instance:\n{str(e)}"
            )
            return None

    def _add_image_layer(self):
        """Add an Earth Engine Image layer."""
        if ee is None:
            QMessageBox.warning(
                self,
                "Warning",
                "Earth Engine API not available. Please install earthengine-api.",
            )
            return

        asset_id = self.image_id_input.text().strip()
        if not asset_id:
            QMessageBox.warning(self, "Warning", "Please enter an asset ID.")
            return

        # Set waiting cursor
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

        try:
            self._show_progress("Loading image...")
            QCoreApplication.processEvents()  # Update UI

            # Create the image
            image = ee.Image(asset_id)

            # Build visualization parameters
            vis_params = {}

            vis_min = self.vis_min_spin.value()
            vis_max = self.vis_max_spin.value()
            if vis_min != 0 or vis_max != 0:
                vis_params["min"] = vis_min
                vis_params["max"] = vis_max

            palette = self.palette_input.text().strip()
            if palette:
                vis_params["palette"] = [p.strip() for p in palette.split(",")]

            bands = self.bands_input.text().strip()
            if bands:
                vis_params["bands"] = [b.strip() for b in bands.split(",")]

            # Get layer name
            name = self.layer_name_input.text().strip() or asset_id.split("/")[-1]

            # Add the layer
            m = self._get_map()
            if m:
                m.add_layer(image, vis_params, name)
                self._show_success(f"Added layer: {name}")

        except Exception as e:
            self._show_error(f"Failed to add image: {str(e)}")
        finally:
            # Restore cursor
            QApplication.restoreOverrideCursor()

    def _add_fc_layer(self):
        """Add an Earth Engine FeatureCollection layer."""
        if ee is None:
            QMessageBox.warning(
                self,
                "Warning",
                "Earth Engine API not available. Please install earthengine-api.",
            )
            return

        asset_id = self.fc_id_input.text().strip()
        if not asset_id:
            QMessageBox.warning(self, "Warning", "Please enter an asset ID.")
            return

        # Set waiting cursor
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

        try:
            self._show_progress("Loading feature collection...")
            QCoreApplication.processEvents()  # Update UI

            # Create the feature collection
            fc = ee.FeatureCollection(asset_id)

            # Get layer name
            name = self.fc_name_input.text().strip() or asset_id.split("/")[-1]

            # Visualization params
            vis_params = {}
            if self.fc_as_vector.isChecked():
                vis_params["as_vector"] = True
                # Add progress callback for vector loading
                vis_params["_progress_callback"] = self._update_progress_message

            # Add the layer
            m = self._get_map()
            if m:
                m.add_layer(fc, vis_params, name)
                self._show_success(f"Added layer: {name}")

        except Exception as e:
            self._show_error(f"Failed to add feature collection: {str(e)}")
        finally:
            # Restore cursor
            QApplication.restoreOverrideCursor()

    def _update_progress_message(self, message: str):
        """Update the progress message and process events."""
        self.status_label.setText(message)
        QCoreApplication.processEvents()

    def _run_code(self):
        """Execute the user-authored code in the in-plugin Python console.

        Security note: this method intentionally calls ``exec`` on text the
        user typed into the dock's code input. Running arbitrary Python is the
        feature, mirroring QGIS's built-in Python console and the geemap
        notebook workflow. The code runs inside the user's QGIS process with
        the user's own privileges and against an in-process ``ee``/``geemap``
        namespace, so no privilege boundary is being crossed. Bandit B102 is
        suppressed at the call site for this reason; do NOT route any
        non-user-authored input through this method.
        """
        code = self.code_input.toPlainText()
        if not code.strip():
            return

        try:
            # Create execution context
            m = self._get_map()
            if m is None:
                return

            # Create namespace for execution
            namespace = {
                "m": m,
                "Map": type(m),
            }

            # Try to import ee
            try:
                import ee

                namespace["ee"] = ee
            except ImportError:
                pass

            # Try to import geemap
            try:
                import geemap

                namespace["geemap"] = geemap
            except ImportError:
                pass

            # Execute the user-authored code; see _run_code docstring for the
            # security rationale behind suppressing B102 here.
            exec(code, namespace)  # nosec B102

            self.code_output.setPlainText("Code executed successfully!")
            self.code_output.setStyleSheet("color: green;")

        except Exception as e:
            self.code_output.setPlainText(f"Error: {str(e)}")
            self.code_output.setStyleSheet("color: red;")

    def _add_basemap(self):
        """Add a basemap layer."""
        basemap = self.basemap_combo.currentText()

        try:
            m = self._get_map()
            if m:
                m.add_basemap(basemap)
                self._show_success(f"Added basemap: {basemap}")
        except Exception as e:
            self._show_error(f"Failed to add basemap: {str(e)}")

    def _center_on_view(self):
        """Center the map on the current canvas view."""
        try:
            m = self._get_map()
            if m:
                center = m.center
                self._show_success(f"Center: {center[0]:.4f}, {center[1]:.4f}")
        except Exception as e:
            self._show_error(f"Failed to get center: {str(e)}")

    def _clear_ee_layers(self):
        """Clear all Earth Engine layers."""
        try:
            m = self._get_map()
            if m:
                m.clear_layers()
                self._show_success("Cleared all EE layers")
        except Exception as e:
            self._show_error(f"Failed to clear layers: {str(e)}")

    def _show_progress(self, message):
        """Show progress indicator."""
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: blue; font-size: 10px;")

    def _show_success(self, message):
        """Show success message."""
        self.progress_bar.setVisible(False)
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: green; font-size: 10px;")
        self.iface.messageBar().pushSuccess("Geemap", message)

    def _show_error(self, message):
        """Show error message."""
        self.progress_bar.setVisible(False)
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: red; font-size: 10px;")
        QMessageBox.critical(self, "Error", message)

    def closeEvent(self, event):
        """Handle dock widget close event."""
        event.accept()
