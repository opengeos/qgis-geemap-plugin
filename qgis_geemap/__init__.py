"""
QGIS Geemap Plugin

A QGIS plugin that provides geemap functionality for working with
Google Earth Engine data directly in QGIS.
"""

from .qgis_geemap import QgisGeemap


def classFactory(iface):
    """Load QgisGeemap class from file qgis_geemap.

    Args:
        iface: A QGIS interface instance.

    Returns:
        QgisGeemap: The plugin instance.
    """
    return QgisGeemap(iface)
