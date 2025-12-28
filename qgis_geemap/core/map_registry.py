"""
Map Registry for QGIS Geemap

This module provides a global registry for Map instances to allow
sharing EE layer references across the plugin.
"""

from typing import Dict, Optional, Any

# Global registry to store the active Map instance
_active_map = None


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


def get_ee_layers() -> Dict[str, tuple]:
    """Get the EE layers from the active Map instance.

    Returns:
        Dictionary of layer name -> (ee_object, vis_params) or empty dict.
    """
    global _active_map
    if _active_map is not None and hasattr(_active_map, "_ee_layers"):
        return _active_map._ee_layers
    return {}


def clear_active_map():
    """Clear the active Map instance."""
    global _active_map
    _active_map = None
