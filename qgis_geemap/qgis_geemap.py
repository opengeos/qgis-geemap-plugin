"""
QGIS Geemap - Main Plugin Class

This module contains the main plugin class that manages the QGIS interface
integration, menu items, toolbar buttons, and dockable panels.
"""

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu, QToolBar, QMessageBox


class QgisGeemap:
    """QGIS Geemap plugin implementation class for QGIS."""

    def __init__(self, iface):
        """Constructor.

        Args:
            iface: An interface instance that provides the hook to QGIS.
        """
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = None
        self.toolbar = None

        # Dock widgets (lazy loaded)
        self._geemap_dock = None
        self._settings_dock = None
        self._inspector_dock = None
        self._export_dock = None

        # Map instance
        self._map = None

        # Inspector tool
        self._inspector_tool = None

        # Dependency state
        self._deps_ready = False
        self._deps_initialized = False
        self._deps_signal_connected = False

    def _ensure_deps(self) -> bool:
        """Check if dependencies are installed and loaded.

        Returns True if deps are ready. If not, shows a non-blocking
        warning and offers to open Settings -> Dependencies tab.
        Does NOT block the UI with a modal dialog.

        Returns:
            True if dependencies are ready and loaded, False otherwise.
        """
        if self._deps_ready:
            return True

        from .core.venv_manager import ensure_venv_packages_available, get_venv_status

        is_ready, status_msg = get_venv_status()

        if is_ready:
            if ensure_venv_packages_available():
                self._deps_ready = True
                self._post_deps_init()
                return True

        # Dependencies not ready -- show non-blocking warning
        self._check_dependencies_on_open()
        return False

    def _check_dependencies_on_open(self):
        """Check if dependencies are installed and prompt if missing."""
        try:
            from .core.venv_manager import check_dependencies

            all_ok, missing, _installed = check_dependencies()
            if all_ok:
                return

            missing_names = ", ".join(name for name, _ in missing)
            reply = QMessageBox.warning(
                self.iface.mainWindow(),
                "Missing Dependencies",
                f"The following required packages are not installed:\n\n"
                f"  {missing_names}\n\n"
                f"The Geemap plugin needs these packages to function.\n\n"
                f"Would you like to open Settings to install them?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )

            if reply == QMessageBox.Yes:
                self._open_settings_deps_tab()

        except Exception:
            # Don't let dependency check errors prevent other actions
            pass

    def _open_settings_deps_tab(self):
        """Open the Settings dock and switch to the Dependencies tab."""
        if self._settings_dock is None:
            try:
                from .dialogs.settings_dock import SettingsDockWidget

                self._settings_dock = SettingsDockWidget(
                    self.iface, self.iface.mainWindow()
                )
                self._settings_dock.setObjectName("GeemapSettingsDock")
                self._settings_dock.visibilityChanged.connect(
                    self._on_settings_visibility_changed
                )
                self.iface.addDockWidget(Qt.RightDockWidgetArea, self._settings_dock)
                self._connect_deps_signal()
            except Exception as e:
                QMessageBox.critical(
                    self.iface.mainWindow(),
                    "Error",
                    f"Failed to create Settings panel:\n{str(e)}",
                )
                return

        self._settings_dock.show()
        self._settings_dock.raise_()
        self.settings_action.setChecked(True)
        self._settings_dock.show_dependencies_tab()

    def _connect_deps_signal(self):
        """Connect settings dock signals to refresh deps state."""
        if not self._deps_signal_connected and self._settings_dock is not None:
            self._settings_dock.deps_installed.connect(self._on_deps_installed)
            self._settings_dock.auth_succeeded.connect(self._on_auth_completed)
            self._settings_dock.settings_saved.connect(self._try_auto_init_ee)
            self._deps_signal_connected = True

    def _on_deps_installed(self):
        """Handle successful dependency installation from settings dock."""
        from .core.venv_manager import ensure_venv_packages_available

        if ensure_venv_packages_available():
            self._deps_ready = True
            self._post_deps_init()
            self.iface.messageBar().pushSuccess(
                "Geemap",
                "Dependencies installed! You can now use all Geemap features.",
            )

    def _on_auth_completed(self):
        """Handle successful EE authentication from the settings dock.

        Tries to initialize EE, and if no project ID is configured yet,
        opens the Settings panel on the Earth Engine tab so the user can
        enter one.
        """
        from .core.ee_layer import is_ee_initialized

        self._try_auto_init_ee()

        if not is_ee_initialized():
            # Project ID not set yet — open Settings on the EE tab
            self._show_settings_ee_tab()

    def _show_settings_ee_tab(self):
        """Open the Settings dock and switch to the Earth Engine tab."""
        if self._settings_dock is None:
            try:
                from .dialogs.settings_dock import SettingsDockWidget

                self._settings_dock = SettingsDockWidget(
                    self.iface, self.iface.mainWindow()
                )
                self._settings_dock.setObjectName("GeemapSettingsDock")
                self._settings_dock.visibilityChanged.connect(
                    self._on_settings_visibility_changed
                )
                self.iface.addDockWidget(Qt.RightDockWidgetArea, self._settings_dock)
                self._connect_deps_signal()
            except Exception as e:
                QMessageBox.critical(
                    self.iface.mainWindow(),
                    "Error",
                    f"Failed to create Settings panel:\n{str(e)}",
                )
                return
        else:
            self._settings_dock.show()
            self._settings_dock.raise_()
        if self._settings_dock is not None:
            self._settings_dock.show_ee_tab()
            self.iface.messageBar().pushInfo(
                "Geemap",
                "Please enter your Google Cloud project ID and click Save Settings.",
            )

    def _post_deps_init(self):
        """One-time initialization after dependencies are confirmed ready."""
        if self._deps_initialized:
            return
        self._deps_initialized = True
        self._patch_geemap()
        self._try_auto_init_ee()

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        checkable=False,
        parent=None,
    ):
        """Add a toolbar icon to the toolbar.

        Args:
            icon_path: Path to the icon for this action.
            text: Text that appears in the menu for this action.
            callback: Function to be called when the action is triggered.
            enabled_flag: A flag indicating if the action should be enabled.
            add_to_menu: Flag indicating whether action should be added to menu.
            add_to_toolbar: Flag indicating whether action should be added to toolbar.
            status_tip: Optional text to show in status bar when mouse hovers over action.
            checkable: Whether the action is checkable (toggle).
            parent: Parent widget for the new action.

        Returns:
            The action that was created.
        """
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)
        action.setCheckable(checkable)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.menu.addAction(action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        # Create menu
        self.menu = QMenu("&Geemap")
        self.iface.mainWindow().menuBar().addMenu(self.menu)

        # Create toolbar
        self.toolbar = QToolBar("Geemap Toolbar")
        self.toolbar.setObjectName("GeemapToolbar")
        self.iface.addToolBar(self.toolbar)

        # Get icon paths
        icon_base = os.path.join(self.plugin_dir, "icons")

        # Main panel icon
        main_icon = os.path.join(icon_base, "icon.svg")
        if not os.path.exists(main_icon):
            main_icon = ":/images/themes/default/mActionAddRasterLayer.svg"

        settings_icon = os.path.join(icon_base, "settings.svg")
        if not os.path.exists(settings_icon):
            settings_icon = ":/images/themes/default/mActionOptions.svg"

        about_icon = os.path.join(icon_base, "about.svg")
        if not os.path.exists(about_icon):
            about_icon = ":/images/themes/default/mActionHelpContents.svg"

        # Initialize EE icon
        init_icon = os.path.join(icon_base, "earth.svg")
        if not os.path.exists(init_icon):
            init_icon = ":/images/themes/default/mIconGlobe.svg"

        # Inspector icon - prefer QGIS built-in for reliability
        inspector_icon = os.path.join(icon_base, "inspector.svg")
        if not os.path.exists(inspector_icon):
            inspector_icon = ":/images/themes/default/mActionIdentify.svg"

        # Export icon - use QGIS built-in download icon for reliability
        export_icon = ":/images/themes/default/mActionFileSaveAs.svg"
        custom_export_icon = os.path.join(icon_base, "export.svg")
        if os.path.exists(custom_export_icon):
            # Check if the icon loads properly
            test_icon = QIcon(custom_export_icon)
            if not test_icon.isNull():
                export_icon = custom_export_icon

        # Add Geemap Panel action (checkable for dock toggle)
        self.geemap_action = self.add_action(
            main_icon,
            "Geemap Panel",
            self.toggle_geemap_dock,
            status_tip="Toggle Geemap Panel",
            checkable=True,
            parent=self.iface.mainWindow(),
        )

        # Add Initialize Earth Engine action
        self.add_action(
            init_icon,
            "Initialize Earth Engine",
            self.initialize_ee,
            status_tip="Initialize Google Earth Engine",
            parent=self.iface.mainWindow(),
        )

        # Add Inspector tool action (checkable)
        self.inspector_action = self.add_action(
            inspector_icon,
            "Inspector",
            self.toggle_inspector,
            status_tip="Inspect Earth Engine layers at click location",
            checkable=True,
            parent=self.iface.mainWindow(),
        )

        # Add Export action (checkable for dock toggle)
        self.export_action = self.add_action(
            export_icon,
            "Export Image",
            self.toggle_export_dock,
            status_tip="Export Earth Engine image to file",
            checkable=True,
            parent=self.iface.mainWindow(),
        )

        # Add Settings Panel action (checkable for dock toggle)
        self.settings_action = self.add_action(
            settings_icon,
            "Settings",
            self.toggle_settings_dock,
            status_tip="Toggle Settings Panel",
            checkable=True,
            parent=self.iface.mainWindow(),
        )

        # Add separator to menu
        self.menu.addSeparator()

        # Update icon
        update_icon = ":/images/themes/default/mActionRefresh.svg"

        # Add Check for Updates action (menu only)
        self.add_action(
            update_icon,
            "Check for Updates...",
            self.show_update_checker,
            add_to_toolbar=False,
            status_tip="Check for plugin updates from GitHub",
            parent=self.iface.mainWindow(),
        )

        # Add About action (menu only)
        self.add_action(
            about_icon,
            "About Geemap",
            self.show_about,
            add_to_toolbar=False,
            status_tip="About QGIS Geemap",
            parent=self.iface.mainWindow(),
        )

    def unload(self):
        """Remove the plugin menu item and icon from QGIS GUI."""
        # Restore original geemap.Map if patched
        self._unpatch_geemap()

        # Remove inspector tool
        if self._inspector_tool:
            self.iface.mapCanvas().unsetMapTool(self._inspector_tool)
            self._inspector_tool = None

        # Remove dock widgets
        if self._geemap_dock:
            self.iface.removeDockWidget(self._geemap_dock)
            self._geemap_dock.deleteLater()
            self._geemap_dock = None

        if self._settings_dock:
            self.iface.removeDockWidget(self._settings_dock)
            self._settings_dock.deleteLater()
            self._settings_dock = None

        if self._inspector_dock:
            self.iface.removeDockWidget(self._inspector_dock)
            self._inspector_dock.deleteLater()
            self._inspector_dock = None

        if self._export_dock:
            self.iface.removeDockWidget(self._export_dock)
            self._export_dock.deleteLater()
            self._export_dock = None

        # Remove actions from menu
        for action in self.actions:
            self.iface.removePluginMenu("&Geemap", action)

        # Remove toolbar
        if self.toolbar:
            del self.toolbar

        # Remove menu
        if self.menu:
            self.menu.deleteLater()

    def _patch_geemap(self):
        """Patch geemap.Map to use QGIS Map class."""
        try:
            from .core.qgis_map import patch_geemap

            patch_geemap()
        except Exception as e:
            # Silently fail if geemap is not installed
            pass

    def _unpatch_geemap(self):
        """Restore original geemap.Map class."""
        try:
            import geemap

            if hasattr(geemap, "_OriginalMap"):
                geemap.Map = geemap._OriginalMap
                delattr(geemap, "_OriginalMap")
        except Exception:
            pass

    def _try_auto_init_ee(self):
        """Try to auto-initialize Earth Engine using settings or env var."""
        try:
            from qgis.PyQt.QtCore import QSettings
            from .core.ee_layer import initialize_ee, is_ee_initialized

            if is_ee_initialized():
                return

            # Read project ID from plugin settings
            settings = QSettings()
            project_id = settings.value("QgisGeemap/project_id", "", type=str)
            if project_id:
                project_id = project_id.strip()
                if not project_id:
                    project_id = None

            # Fall back to environment variable
            if not project_id:
                project_id = os.environ.get("EE_PROJECT_ID", None)

            if project_id:
                try:
                    from qgis.core import QgsMessageLog, Qgis

                    QgsMessageLog.logMessage(
                        f"Auto-initializing Earth Engine with project: {project_id}",
                        "Geemap",
                        Qgis.Info,
                    )
                    initialize_ee(project=project_id)
                except Exception as exc:
                    from qgis.core import QgsMessageLog, Qgis

                    QgsMessageLog.logMessage(
                        f"Auto-init EE failed: {exc}",
                        "Geemap",
                        Qgis.Warning,
                    )
        except ImportError:
            pass

    def initialize_ee(self):
        """Initialize Google Earth Engine."""
        if not self._ensure_deps():
            return
        try:
            from .core.ee_layer import initialize_ee

            initialize_ee()
            self.iface.messageBar().pushSuccess(
                "Geemap", "Earth Engine initialized successfully!"
            )
        except ImportError as e:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Error",
                f"Earth Engine API not found. Please install earthengine-api:\n\n"
                f"pip install earthengine-api\n\nError: {str(e)}",
            )
        except Exception as e:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Error",
                f"Failed to initialize Earth Engine:\n\n{str(e)}\n\n"
                "You may need to authenticate using: earthengine authenticate",
            )

    def toggle_geemap_dock(self):
        """Toggle the Geemap dock widget visibility."""
        if not self._ensure_deps():
            self.geemap_action.setChecked(False)
            return
        if self._geemap_dock is None:
            try:
                from .dialogs.geemap_dock import GeemapDockWidget

                self._geemap_dock = GeemapDockWidget(
                    self.iface, self.iface.mainWindow()
                )
                self._geemap_dock.setObjectName("GeemapDock")
                self._geemap_dock.visibilityChanged.connect(
                    self._on_geemap_visibility_changed
                )
                self.iface.addDockWidget(Qt.RightDockWidgetArea, self._geemap_dock)
                self._geemap_dock.show()
                self._geemap_dock.raise_()
                return

            except Exception as e:
                QMessageBox.critical(
                    self.iface.mainWindow(),
                    "Error",
                    f"Failed to create Geemap panel:\n{str(e)}",
                )
                self.geemap_action.setChecked(False)
                return

        # Toggle visibility
        if self._geemap_dock.isVisible():
            self._geemap_dock.hide()
        else:
            self._geemap_dock.show()
            self._geemap_dock.raise_()

    def _on_geemap_visibility_changed(self, visible):
        """Handle Geemap dock visibility change."""
        self.geemap_action.setChecked(visible)

    def toggle_settings_dock(self):
        """Toggle the Settings dock widget visibility.

        Settings must be accessible even without dependencies installed,
        because the Dependencies tab is how users install them.
        """
        if self._settings_dock is None:
            try:
                from .dialogs.settings_dock import SettingsDockWidget

                self._settings_dock = SettingsDockWidget(
                    self.iface, self.iface.mainWindow()
                )
                self._settings_dock.setObjectName("GeemapSettingsDock")
                self._settings_dock.visibilityChanged.connect(
                    self._on_settings_visibility_changed
                )
                self.iface.addDockWidget(Qt.RightDockWidgetArea, self._settings_dock)
                self._settings_dock.show()
                self._settings_dock.raise_()
                self._connect_deps_signal()
                return

            except Exception as e:
                QMessageBox.critical(
                    self.iface.mainWindow(),
                    "Error",
                    f"Failed to create Settings panel:\n{str(e)}",
                )
                self.settings_action.setChecked(False)
                return

        # Toggle visibility
        if self._settings_dock.isVisible():
            self._settings_dock.hide()
        else:
            self._settings_dock.show()
            self._settings_dock.raise_()

    def _on_settings_visibility_changed(self, visible):
        """Handle Settings dock visibility change."""
        self.settings_action.setChecked(visible)

    def toggle_inspector(self):
        """Toggle the Inspector tool."""
        if not self._ensure_deps():
            self.inspector_action.setChecked(False)
            return
        if self._inspector_tool is None:
            try:
                from .dialogs.inspector_tool import (
                    InspectorMapTool,
                    InspectorDockWidget,
                )

                # Create inspector dock if not exists
                if self._inspector_dock is None:
                    self._inspector_dock = InspectorDockWidget(
                        self.iface, self.iface.mainWindow()
                    )
                    self._inspector_dock.setObjectName("GeemapInspectorDock")
                    self.iface.addDockWidget(
                        Qt.RightDockWidgetArea, self._inspector_dock
                    )

                # Create and activate the map tool
                self._inspector_tool = InspectorMapTool(
                    self.iface.mapCanvas(), self._inspector_dock
                )
                self._inspector_tool.deactivated.connect(self._on_inspector_deactivated)
                self.iface.mapCanvas().setMapTool(self._inspector_tool)
                self._inspector_dock.show()
                self._inspector_dock.raise_()
                self.inspector_action.setChecked(True)
                return

            except Exception as e:
                QMessageBox.critical(
                    self.iface.mainWindow(),
                    "Error",
                    f"Failed to create Inspector tool:\n{str(e)}",
                )
                self.inspector_action.setChecked(False)
                return

        # Toggle the tool
        if self.iface.mapCanvas().mapTool() == self._inspector_tool:
            self.iface.mapCanvas().unsetMapTool(self._inspector_tool)
            self.inspector_action.setChecked(False)
            if self._inspector_dock:
                self._inspector_dock.hide()
        else:
            self.iface.mapCanvas().setMapTool(self._inspector_tool)
            self.inspector_action.setChecked(True)
            if self._inspector_dock:
                self._inspector_dock.show()
                self._inspector_dock.raise_()

    def _on_inspector_deactivated(self):
        """Handle Inspector tool deactivation."""
        self.inspector_action.setChecked(False)

    def toggle_export_dock(self):
        """Toggle the Export dock widget visibility."""
        if not self._ensure_deps():
            self.export_action.setChecked(False)
            return
        if self._export_dock is None:
            try:
                from .dialogs.export_dock import ExportDockWidget

                self._export_dock = ExportDockWidget(
                    self.iface, self.iface.mainWindow()
                )
                self._export_dock.setObjectName("GeemapExportDock")
                self._export_dock.visibilityChanged.connect(
                    self._on_export_visibility_changed
                )
                self.iface.addDockWidget(Qt.RightDockWidgetArea, self._export_dock)
                self._export_dock.show()
                self._export_dock.raise_()
                return

            except Exception as e:
                QMessageBox.critical(
                    self.iface.mainWindow(),
                    "Error",
                    f"Failed to create Export panel:\n{str(e)}",
                )
                self.export_action.setChecked(False)
                return

        # Toggle visibility
        if self._export_dock.isVisible():
            self._export_dock.hide()
        else:
            self._export_dock.show()
            self._export_dock.raise_()

    def _on_export_visibility_changed(self, visible):
        """Handle Export dock visibility change."""
        self.export_action.setChecked(visible)

    def show_about(self):
        """Display the about dialog."""
        # Read version from metadata.txt
        version = "Unknown"
        try:
            metadata_path = os.path.join(self.plugin_dir, "metadata.txt")
            with open(metadata_path, "r", encoding="utf-8") as f:
                import re

                content = f.read()
                version_match = re.search(r"^version=(.+)$", content, re.MULTILINE)
                if version_match:
                    version = version_match.group(1).strip()
        except Exception as e:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Geemap",
                f"Could not read version from metadata.txt:\n{str(e)}",
            )

        about_text = f"""
<h2>QGIS Geemap Plugin</h2>
<p>Version: {version}</p>
<p>Author: Qiusheng Wu</p>

<h3>Description:</h3>
<p>A QGIS plugin that integrates geemap for working with Google Earth Engine data directly in QGIS.</p>

<h3>Features:</h3>
<ul>
<li><b>Earth Engine Images:</b> Add Earth Engine Image and ImageCollection layers</li>
<li><b>Vector Data:</b> Add FeatureCollections as vector or styled raster layers</li>
<li><b>Familiar API:</b> Use geemap.Map() API directly in QGIS Python console</li>
<li><b>Interactive Panel:</b> GUI panel for common Earth Engine operations</li>
</ul>

<h3>Usage:</h3>
<pre>
import ee
import geemap

m = geemap.Map(center=(40, -100), zoom=4)
dem = ee.Image("USGS/SRTMGL1_003")
m.add_layer(dem, {{"min": 0, "max": 4000}}, "DEM")
</pre>

<h3>Links:</h3>
<ul>
<li><a href="https://github.com/opengeos/qgis-geemap-plugin">GitHub Repository</a></li>
<li><a href="https://geemap.org">Geemap Documentation</a></li>
<li><a href="https://github.com/opengeos/qgis-geemap-plugin/issues">Report Issues</a></li>
</ul>

<p>Licensed under MIT License</p>
"""
        QMessageBox.about(
            self.iface.mainWindow(),
            "About QGIS Geemap",
            about_text,
        )

    def show_update_checker(self):
        """Display the update checker dialog."""
        try:
            from .dialogs.update_checker import UpdateCheckerDialog
        except ImportError as e:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Error",
                f"Failed to import update checker dialog:\n{str(e)}",
            )
            return

        try:
            dialog = UpdateCheckerDialog(self.plugin_dir, self.iface.mainWindow())
            dialog.exec_()
        except Exception as e:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Error",
                f"Failed to open update checker:\n{str(e)}",
            )
