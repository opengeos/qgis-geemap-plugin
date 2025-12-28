"""
Settings Dock Widget for QGIS Geemap

This module provides a settings panel for configuring
Earth Engine authentication and plugin options.
"""

from qgis.PyQt.QtCore import Qt, QSettings
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QGroupBox,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QFormLayout,
    QMessageBox,
    QFileDialog,
    QTabWidget,
)
from qgis.PyQt.QtGui import QFont

try:
    import ee
except ImportError:
    ee = None


class SettingsDockWidget(QDockWidget):
    """A settings panel for configuring geemap options."""

    # Settings keys
    SETTINGS_PREFIX = "QgisGeemap/"

    def __init__(self, iface, parent=None):
        """Initialize the settings dock widget.

        Args:
            iface: QGIS interface instance.
            parent: Parent widget.
        """
        super().__init__("Geemap Settings", parent)
        self.iface = iface
        self.settings = QSettings()

        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        """Set up the settings UI."""
        # Main widget
        main_widget = QWidget()
        self.setWidget(main_widget)

        # Main layout
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(10)

        # Header
        header_label = QLabel("Geemap Settings")
        header_font = QFont()
        header_font.setPointSize(12)
        header_font.setBold(True)
        header_label.setFont(header_font)
        header_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(header_label)

        # Tab widget for organized settings
        tab_widget = QTabWidget()
        layout.addWidget(tab_widget)

        # Earth Engine tab
        ee_tab = self._create_ee_tab()
        tab_widget.addTab(ee_tab, "Earth Engine")

        # General settings tab
        general_tab = self._create_general_tab()
        tab_widget.addTab(general_tab, "General")

        # Buttons
        button_layout = QHBoxLayout()

        self.save_btn = QPushButton("Save Settings")
        self.save_btn.clicked.connect(self._save_settings)
        button_layout.addWidget(self.save_btn)

        self.reset_btn = QPushButton("Reset Defaults")
        self.reset_btn.clicked.connect(self._reset_defaults)
        button_layout.addWidget(self.reset_btn)

        layout.addLayout(button_layout)

        # Stretch at the end
        layout.addStretch()

        # Status label
        self.status_label = QLabel("Settings loaded")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.status_label)

    def _create_ee_tab(self):
        """Create the Earth Engine settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Authentication group
        auth_group = QGroupBox("Authentication")
        auth_layout = QFormLayout(auth_group)

        # Project ID
        self.project_id_input = QLineEdit()
        self.project_id_input.setPlaceholderText("Google Cloud Project ID")
        auth_layout.addRow("Project ID:", self.project_id_input)

        # Service account
        self.service_account_input = QLineEdit()
        self.service_account_input.setPlaceholderText(
            "Optional: service-account@project.iam.gserviceaccount.com"
        )
        auth_layout.addRow("Service Account:", self.service_account_input)

        # Credentials file
        cred_layout = QHBoxLayout()
        self.credentials_input = QLineEdit()
        self.credentials_input.setPlaceholderText("Path to credentials JSON file")
        cred_layout.addWidget(self.credentials_input)
        self.browse_cred_btn = QPushButton("...")
        self.browse_cred_btn.setMaximumWidth(30)
        self.browse_cred_btn.clicked.connect(self._browse_credentials)
        cred_layout.addWidget(self.browse_cred_btn)
        auth_layout.addRow("Credentials:", cred_layout)

        layout.addWidget(auth_group)

        # Actions group
        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout(actions_group)

        # Initialize button
        init_btn = QPushButton("Initialize Earth Engine")
        init_btn.clicked.connect(self._initialize_ee)
        actions_layout.addWidget(init_btn)

        # Authenticate button
        auth_btn = QPushButton("Authenticate (opens browser)")
        auth_btn.clicked.connect(self._authenticate_ee)
        actions_layout.addWidget(auth_btn)

        # Status
        self.ee_status_label = QLabel("Status: Not initialized")
        self.ee_status_label.setStyleSheet("color: gray;")
        actions_layout.addWidget(self.ee_status_label)

        layout.addWidget(actions_group)

        layout.addStretch()
        return widget

    def _create_general_tab(self):
        """Create the general settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Display options group
        display_group = QGroupBox("Display Options")
        display_layout = QFormLayout(display_group)

        # Default zoom
        self.default_zoom_spin = QSpinBox()
        self.default_zoom_spin.setRange(0, 24)
        self.default_zoom_spin.setValue(4)
        display_layout.addRow("Default Zoom:", self.default_zoom_spin)

        # Max features for vector
        self.max_features_spin = QSpinBox()
        self.max_features_spin.setRange(100, 100000)
        self.max_features_spin.setValue(5000)
        self.max_features_spin.setSingleStep(1000)
        display_layout.addRow("Max Vector Features:", self.max_features_spin)

        # Auto-initialize
        self.auto_init_check = QCheckBox()
        self.auto_init_check.setChecked(False)
        # display_layout.addRow("Auto-initialize EE:", self.auto_init_check)

        layout.addWidget(display_group)

        # Basemap options group
        basemap_group = QGroupBox("Default Basemap")
        basemap_layout = QFormLayout(basemap_group)

        self.default_basemap_combo = QComboBox()
        basemaps = [
            "(None)",
            "OpenStreetMap",
            "Google Maps",
            "Google Satellite",
            "CartoDB Positron",
            "CartoDB Dark Matter",
        ]
        self.default_basemap_combo.addItems(basemaps)
        basemap_layout.addRow("Basemap:", self.default_basemap_combo)

        layout.addWidget(basemap_group)

        layout.addStretch()
        return widget

    def _browse_credentials(self):
        """Open file browser for credentials file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Credentials File",
            "",
            "JSON Files (*.json);;All Files (*)",
        )
        if file_path:
            self.credentials_input.setText(file_path)

    def _initialize_ee(self):
        """Initialize Earth Engine with current settings."""
        if ee is None:
            QMessageBox.warning(
                self,
                "Warning",
                "Earth Engine API not installed.\n\n"
                "Install with: pip install earthengine-api",
            )
            return

        try:
            project = self.project_id_input.text().strip() or None

            # Check if credentials file is specified
            cred_file = self.credentials_input.text().strip()
            credentials = None

            if cred_file:
                from google.oauth2 import service_account

                credentials = service_account.Credentials.from_service_account_file(
                    cred_file,
                    scopes=["https://www.googleapis.com/auth/earthengine"],
                )

            if project:
                ee.Initialize(credentials=credentials, project=project)
            else:
                ee.Initialize(credentials=credentials)

            self.ee_status_label.setText("Status: Initialized ✓")
            self.ee_status_label.setStyleSheet("color: green;")
            self.iface.messageBar().pushSuccess(
                "Geemap", "Earth Engine initialized successfully!"
            )

        except Exception as e:
            self.ee_status_label.setText(f"Status: Error")
            self.ee_status_label.setStyleSheet("color: red;")
            QMessageBox.critical(
                self,
                "Initialization Error",
                f"Failed to initialize Earth Engine:\n\n{str(e)}",
            )

    def _authenticate_ee(self):
        """Authenticate with Earth Engine."""
        if ee is None:
            QMessageBox.warning(
                self,
                "Warning",
                "Earth Engine API not installed.\n\n"
                "Install with: pip install earthengine-api",
            )
            return

        try:
            ee.Authenticate()
            self.ee_status_label.setText(
                "Status: Authenticated (restart may be needed)"
            )
            self.ee_status_label.setStyleSheet("color: green;")
            self.iface.messageBar().pushSuccess(
                "Geemap",
                "Authentication complete. You may need to initialize Earth Engine.",
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Authentication Error",
                f"Failed to authenticate:\n\n{str(e)}",
            )

    def _load_settings(self):
        """Load settings from QSettings."""
        # Earth Engine
        self.project_id_input.setText(
            self.settings.value(f"{self.SETTINGS_PREFIX}project_id", "", type=str)
        )
        self.service_account_input.setText(
            self.settings.value(f"{self.SETTINGS_PREFIX}service_account", "", type=str)
        )
        self.credentials_input.setText(
            self.settings.value(f"{self.SETTINGS_PREFIX}credentials", "", type=str)
        )

        # General
        self.default_zoom_spin.setValue(
            self.settings.value(f"{self.SETTINGS_PREFIX}default_zoom", 4, type=int)
        )
        self.max_features_spin.setValue(
            self.settings.value(f"{self.SETTINGS_PREFIX}max_features", 5000, type=int)
        )
        self.auto_init_check.setChecked(
            self.settings.value(f"{self.SETTINGS_PREFIX}auto_init", False, type=bool)
        )
        self.default_basemap_combo.setCurrentIndex(
            self.settings.value(f"{self.SETTINGS_PREFIX}default_basemap", 0, type=int)
        )

        self.status_label.setText("Settings loaded")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")

    def _save_settings(self):
        """Save settings to QSettings."""
        # Earth Engine
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}project_id", self.project_id_input.text()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}service_account", self.service_account_input.text()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}credentials", self.credentials_input.text()
        )

        # General
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}default_zoom", self.default_zoom_spin.value()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}max_features", self.max_features_spin.value()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}auto_init", self.auto_init_check.isChecked()
        )
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}default_basemap",
            self.default_basemap_combo.currentIndex(),
        )

        self.settings.sync()

        self.status_label.setText("Settings saved")
        self.status_label.setStyleSheet("color: green; font-size: 10px;")

        self.iface.messageBar().pushSuccess("Geemap", "Settings saved successfully!")

    def _reset_defaults(self):
        """Reset all settings to defaults."""
        reply = QMessageBox.question(
            self,
            "Reset Settings",
            "Are you sure you want to reset all settings to defaults?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        # Earth Engine
        self.project_id_input.clear()
        self.service_account_input.clear()
        self.credentials_input.clear()

        # General
        self.default_zoom_spin.setValue(4)
        self.max_features_spin.setValue(5000)
        self.auto_init_check.setChecked(False)
        self.default_basemap_combo.setCurrentIndex(0)

        self.status_label.setText("Defaults restored (not saved)")
        self.status_label.setStyleSheet("color: orange; font-size: 10px;")
