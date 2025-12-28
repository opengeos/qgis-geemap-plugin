"""
QGIS Geemap Core Module

This module contains the core functionality for integrating
geemap with QGIS.
"""

from .qgis_map import Map
from .ee_layer import (
    ee_to_qgis_layer,
    get_ee_tile_url,
    ee_feature_collection_to_vector,
    ee_geometry_to_vector,
    initialize_ee,
    try_auto_initialize_ee,
    is_ee_initialized,
    colormap_to_palette,
    is_matplotlib_colormap,
    process_vis_params,
)
from .map_registry import (
    get_active_map,
    set_active_map,
    get_ee_layers,
    clear_active_map,
)

__all__ = [
    "Map",
    "ee_to_qgis_layer",
    "get_ee_tile_url",
    "ee_feature_collection_to_vector",
    "ee_geometry_to_vector",
    "initialize_ee",
    "try_auto_initialize_ee",
    "is_ee_initialized",
    "colormap_to_palette",
    "is_matplotlib_colormap",
    "process_vis_params",
    "get_active_map",
    "set_active_map",
    "get_ee_layers",
    "clear_active_map",
]
