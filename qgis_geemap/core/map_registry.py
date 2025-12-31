"""
Map Registry for QGIS Geemap

This module provides a global registry for Map instances to allow
sharing EE layer references across the plugin.
"""

from typing import Dict, Optional, Any

# Global registry to store the active Map instance
_active_map = None

# Global registry to store ALL EE layers from all Map instances
_global_ee_layers = {}

# Global registry to map QGIS layer IDs to EE layer names
_global_layer_ids = {}


def get_active_map():
    """Get the active Map instance.

    Returns:
        The active Map instance or None if not set.
    """
    global _active_map
    return _active_map


def set_active_map(map_instance):
    """Set the active Map instance.

    Args:
        map_instance: The Map instance to set as active.
    """
    global _active_map
    _active_map = map_instance


def register_ee_layer(
    name: str, ee_object: Any, vis_params: Dict, layer_id: str = None
):
    """Register an EE layer globally.

    Args:
        name: Layer name.
        ee_object: Earth Engine object.
        vis_params: Visualization parameters.
        layer_id: QGIS layer ID (optional, for cleanup tracking).
    """
    global _global_ee_layers, _global_layer_ids
    _global_ee_layers[name] = (ee_object, vis_params)
    if layer_id:
        _global_layer_ids[layer_id] = name


def unregister_ee_layer(name: str):
    """Unregister an EE layer.

    Args:
        name: Layer name to remove.
    """
    global _global_ee_layers, _global_layer_ids
    if name in _global_ee_layers:
        del _global_ee_layers[name]

    # Also remove from layer ID mapping
    layer_id_to_remove = None
    for lid, lname in _global_layer_ids.items():
        if lname == name:
            layer_id_to_remove = lid
            break
    if layer_id_to_remove:
        del _global_layer_ids[layer_id_to_remove]


def get_ee_layers() -> Dict[str, tuple]:
    """Get all registered EE layers from all Map instances.

    Returns:
        Dictionary of layer name -> (ee_object, vis_params) or empty dict.
    """
    global _global_ee_layers
    return _global_ee_layers.copy()


def clear_active_map():
    """Clear the active Map instance."""
    global _active_map
    _active_map = None


def clear_all_ee_layers():
    """Clear all registered EE layers."""
    global _global_ee_layers, _global_layer_ids
    _global_ee_layers = {}
    _global_layer_ids = {}


def cleanup_removed_layers(layer_ids):
    """Clean up EE layers that were removed from QGIS.

    Args:
        layer_ids: List of QGIS layer IDs that were removed.
    """
    global _global_layer_ids, _global_ee_layers

    for layer_id in layer_ids:
        if layer_id in _global_layer_ids:
            name = _global_layer_ids[layer_id]

            # Remove from both registries
            if name in _global_ee_layers:
                del _global_ee_layers[name]
            del _global_layer_ids[layer_id]
