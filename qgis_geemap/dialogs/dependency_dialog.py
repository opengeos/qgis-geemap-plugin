"""Dependency Installation Dialog for QGIS Geemap Plugin.

Provides a modal dialog that installs required Python packages
(earthengine-api, geemap, google-auth-oauthlib) into an isolated
virtual environment at ~/.qgis_geemap.
"""

import traceback

from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)


class DepsInstallWorker(QThread):
    """Background worker thread for dependency installation.

    Runs the venv creation and package installation in a separate thread
    to keep the QGIS UI responsive.
    """

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        """Initialize the worker.

        Args:
            parent: Parent QObject.
        """
        super().__init__(parent)
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the installation."""
        self._cancelled = True

    def run(self):
        """Execute the installation in the background thread."""
        try:
            from ..core.venv_manager import create_venv_and_install

            success, message = create_venv_and_install(
                progress_callback=lambda p, m: self.progress.emit(p, m),
                cancel_check=lambda: self._cancelled,
            )
            self.finished.emit(success, message)
        except Exception as e:
            self.finished.emit(False, f"{e}\n{traceback.format_exc()}")


class DependencyInstallDialog(QDialog):
    """Modal dialog for installing geemap dependencies.

    Shows a progress bar and status messages while packages are installed
    into an isolated virtual environment.
    """

    def __init__(self, parent=None):
        """Initialize the dialog.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self._worker = None
        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Install Dependencies")
        self.setMinimumWidth(480)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Title
        title = QLabel("Install Dependencies")
        font = title.font()
        font.setPointSize(14)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "The Geemap plugin requires additional Python packages to function. "
            "These will be installed into an isolated environment that will not "
            "affect your QGIS Python installation."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Package list
        packages_label = QLabel(
            "<b>Packages to install:</b>"
            "<ul>"
            "<li>earthengine-api (Google Earth Engine Python API)</li>"
            "<li>geemap (Interactive mapping with Earth Engine)</li>"
            "<li>google-auth-oauthlib (Authentication support)</li>"
            "</ul>"
        )
        packages_label.setTextFormat(Qt.RichText)
        layout.addWidget(packages_label)

        # Install location
        location_label = QLabel("<b>Install location:</b> <code>~/.qgis_geemap</code>")
        location_label.setTextFormat(Qt.RichText)
        layout.addWidget(location_label)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        # Status label
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._install_btn = QPushButton("Install")
        self._install_btn.setDefault(True)
        self._install_btn.clicked.connect(self._on_install_clicked)
        button_layout.addWidget(self._install_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        button_layout.addWidget(self._cancel_btn)

        layout.addLayout(button_layout)

    def _on_install_clicked(self):
        """Start the dependency installation."""
        self._install_btn.setEnabled(False)
        self._install_btn.setText("Installing...")
        self._cancel_btn.setText("Cancel Installation")
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._status_label.setVisible(True)
        self._status_label.setText("Starting installation...")

        self._worker = DepsInstallWorker(self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_cancel_clicked(self):
        """Handle cancel button click."""
        if self._worker and self._worker.isRunning():
            self._status_label.setText("Cancelling...")
            self._cancel_btn.setEnabled(False)
            self._worker.cancel()
            self._worker.wait(10000)
        else:
            self.reject()

    def _on_progress(self, percent: int, message: str):
        """Update progress bar and status label.

        Args:
            percent: Progress percentage (0-100).
            message: Status message to display.
        """
        self._progress_bar.setValue(percent)
        self._status_label.setText(message)

    def _on_finished(self, success: bool, message: str):
        """Handle installation completion.

        Args:
            success: Whether installation succeeded.
            message: Result message.
        """
        self._worker = None

        if success:
            self._progress_bar.setValue(100)
            self._status_label.setText("Dependencies installed successfully!")
            self.accept()
        else:
            self._progress_bar.setVisible(False)
            self._status_label.setText(f"Installation failed: {message}")

            QMessageBox.warning(
                self,
                "Installation Failed",
                f"Failed to install dependencies:\n\n{message}\n\n"
                "You can try again by clicking Install.",
            )

            self._install_btn.setEnabled(True)
            self._install_btn.setText("Retry Install")
            self._cancel_btn.setEnabled(True)
            self._cancel_btn.setText("Cancel")

    def closeEvent(self, event):
        """Handle dialog close event.

        Args:
            event: The close event.
        """
        if self._worker and self._worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)
