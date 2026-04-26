"""Shared pytest fixtures.

Stubs the ``qgis`` package so the plugin's modules can be imported without a
running QGIS instance. The stub reproduces the real ``qgis.PyQt`` shim
behavior: on Qt6 it re-exports ``QAction``, ``QActionGroup`` and ``QShortcut``
from ``QtGui`` under ``qgis.PyQt.QtWidgets`` (they moved out of ``QtWidgets``
in Qt6); on Qt5 those classes already live in ``QtWidgets`` so no re-export
is needed.

The Qt binding is selected by the ``QT_BINDING`` env var (defaults to PyQt6,
the migration target). CI runs the matrix under both bindings to catch
regressions in either direction.
"""

import importlib
import os
import sys
import types
from unittest.mock import MagicMock

QT_BINDING = os.environ.get("QT_BINDING", "PyQt6")

QtCore = importlib.import_module(f"{QT_BINDING}.QtCore")
QtGui = importlib.import_module(f"{QT_BINDING}.QtGui")
QtNetwork = importlib.import_module(f"{QT_BINDING}.QtNetwork")
QtWidgets = importlib.import_module(f"{QT_BINDING}.QtWidgets")


def _install_qgis_stub() -> None:
    qgis = types.ModuleType("qgis")
    qgis.__path__ = []
    sys.modules["qgis"] = qgis

    qgis_pyqt = types.ModuleType("qgis.PyQt")
    qgis_pyqt.__path__ = []
    sys.modules["qgis.PyQt"] = qgis_pyqt
    qgis.PyQt = qgis_pyqt

    pyqt_submodules = {
        "QtCore": QtCore,
        "QtGui": QtGui,
        "QtNetwork": QtNetwork,
        "QtWidgets": QtWidgets,
    }
    for name, real in pyqt_submodules.items():
        alias = types.ModuleType(f"qgis.PyQt.{name}")
        for attr in dir(real):
            if not attr.startswith("_"):
                setattr(alias, attr, getattr(real, attr))
        sys.modules[f"qgis.PyQt.{name}"] = alias
        setattr(qgis_pyqt, name, alias)

    # Qt6: QAction, QActionGroup, and QShortcut live in QtGui. The real
    # qgis.PyQt.QtWidgets shim re-exports them, so mirror that here. On Qt5
    # they're already on QtWidgets, so the lookup falls through to QtWidgets
    # itself and no extra wiring is required.
    qtwidgets_alias = sys.modules["qgis.PyQt.QtWidgets"]
    for attr in ("QAction", "QActionGroup", "QShortcut"):
        if hasattr(QtGui, attr):
            setattr(qtwidgets_alias, attr, getattr(QtGui, attr))

    for submodule in ("QtSvg", "QtWebEngineWidgets"):
        alias = MagicMock()
        sys.modules[f"qgis.PyQt.{submodule}"] = alias
        setattr(qgis_pyqt, submodule, alias)

    for name in ("core", "gui", "utils"):
        stub = MagicMock()
        stub.__spec__ = None
        sys.modules[f"qgis.{name}"] = stub
        setattr(qgis, name, stub)


_install_qgis_stub()
