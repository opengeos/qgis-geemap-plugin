"""
Earth Engine to QGIS Layer Conversion Utilities

This module provides functions to convert Earth Engine objects to QGIS layers.
"""

import json
import os
import tempfile
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    import ee
except ImportError:
    ee = None

try:
    import matplotlib
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

from qgis.core import (
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsField,
    QgsFields,
    QgsPointXY,
    QgsWkbTypes,
    QgsApplication,
    QgsTask,
    QgsMessageLog,
    Qgis,
)
from qgis.PyQt.QtCore import QVariant, QThread, pyqtSignal, QObject


# Track if EE has been initialized
_ee_initialized = False


def is_matplotlib_colormap(palette: Any) -> bool:
    """Check if the palette is a matplotlib colormap name.
    
    Args:
        palette: A palette value (string or list).
        
    Returns:
        True if palette is a valid matplotlib colormap name.
    """
    if not HAS_MATPLOTLIB:
        return False
    
    if not isinstance(palette, str):
        return False
    
    # Check if it's a known matplotlib colormap
    try:
        plt.get_cmap(palette)
        return True
    except (ValueError, TypeError):
        return False


def colormap_to_palette(
    colormap: str,
    n_colors: int = 256,
) -> List[str]:
    """Convert a matplotlib colormap to a list of hex colors.
    
    Args:
        colormap: Name of a matplotlib colormap (e.g., "terrain", "viridis").
        n_colors: Number of colors to generate.
        
    Returns:
        List of hex color strings.
    """
    if not HAS_MATPLOTLIB:
        raise ImportError(
            "matplotlib is required for colormap support. "
            "Please install it with: pip install matplotlib"
        )
    
    try:
        cmap = plt.get_cmap(colormap, n_colors)
        colors = []
        for i in range(n_colors):
            rgba = cmap(i / (n_colors - 1) if n_colors > 1 else 0)
            # Convert to hex
            hex_color = "#{:02x}{:02x}{:02x}".format(
                int(rgba[0] * 255),
                int(rgba[1] * 255),
                int(rgba[2] * 255),
            )
            colors.append(hex_color)
        return colors
    except Exception as e:
        raise ValueError(f"Failed to convert colormap '{colormap}': {e}")


def process_vis_params(vis_params: Optional[Dict]) -> Dict:
    """Process visualization parameters, converting matplotlib colormaps if needed.
    
    Args:
        vis_params: Visualization parameters dictionary.
        
    Returns:
        Processed visualization parameters with palette converted if needed.
    """
    if vis_params is None:
        return {}
    
    # Make a copy to avoid modifying the original
    processed = vis_params.copy()
    
    # Check if palette needs conversion
    palette = processed.get("palette")
    if palette is not None:
        if isinstance(palette, str):
            # Check if it's a matplotlib colormap
            if is_matplotlib_colormap(palette):
                # Convert colormap to list of hex colors
                processed["palette"] = colormap_to_palette(palette)
            elif "," in palette:
                # Handle comma-separated color string
                processed["palette"] = [c.strip() for c in palette.split(",")]
            # Otherwise leave as-is (might be a single color name)
        elif isinstance(palette, (list, tuple)):
            # Already a list, ensure it's a regular list
            processed["palette"] = list(palette)
    
    return processed


def is_ee_initialized() -> bool:
    """Check if Earth Engine has been initialized."""
    global _ee_initialized
    return _ee_initialized


def initialize_ee(project: str = None, credentials: Any = None) -> bool:
    """Initialize Earth Engine.

    Args:
        project: Google Cloud project ID.
        credentials: Optional credentials object.

    Returns:
        True if initialization was successful, False otherwise.
    """
    global _ee_initialized

    if ee is None:
        raise ImportError(
            "The 'ee' module is not installed. Please install earthengine-api."
        )

    if project is None or project == "":
        project = os.environ.get("EE_PROJECT_ID", None)

    try:
        if project:
            ee.Initialize(credentials=credentials, project=project)
        else:
            ee.Initialize(credentials=credentials)
        _ee_initialized = True
        return True
    except Exception as e:
        # Try to authenticate first
        try:
            ee.Authenticate()
            if project:
                ee.Initialize(credentials=credentials, project=project)
            else:
                ee.Initialize(credentials=credentials)
            _ee_initialized = True
            return True
        except Exception as auth_e:
            raise RuntimeError(
                f"Failed to initialize Earth Engine: {e}\n"
                f"Authentication also failed: {auth_e}"
            )


def try_auto_initialize_ee() -> bool:
    """Try to auto-initialize Earth Engine if EE_PROJECT_ID is set.

    Returns:
        True if initialization was successful, False otherwise.
    """
    global _ee_initialized

    if _ee_initialized:
        return True

    if ee is None:
        return False

    project = os.environ.get("EE_PROJECT_ID", None)
    if not project:
        return False

    try:
        ee.Initialize(project=project)
        _ee_initialized = True
        QgsMessageLog.logMessage(
            f"Earth Engine auto-initialized with project: {project}",
            "Geemap",
            Qgis.Info,
        )
        return True
    except Exception as e:
        QgsMessageLog.logMessage(
            f"Failed to auto-initialize Earth Engine: {e}", "Geemap", Qgis.Warning
        )
        return False


def get_ee_tile_url(
    ee_object: Any,
    vis_params: Optional[Dict] = None,
) -> str:
    """Get an XYZ tile URL for an Earth Engine object.

    Args:
        ee_object: An Earth Engine Image or ImageCollection.
        vis_params: Visualization parameters dictionary.
            Supports matplotlib colormap names as palette (e.g., "terrain", "viridis").

    Returns:
        XYZ tile URL string.
    """
    if ee is None:
        raise ImportError(
            "The 'ee' module is not installed. Please install earthengine-api."
        )

    # Process vis_params to handle matplotlib colormaps
    vis_params = process_vis_params(vis_params)

    # Handle ImageCollection by taking the first image or mosaic
    if isinstance(ee_object, ee.ImageCollection):
        ee_object = ee_object.mosaic()

    # Get the map ID
    map_id_dict = ee_object.getMapId(vis_params)

    # Construct the tile URL
    # The format is: https://earthengine.googleapis.com/v1/{mapid}/tiles/{z}/{x}/{y}
    tile_url = map_id_dict.get("tile_fetcher").url_format

    return tile_url


def get_ee_tile_url_legacy(
    ee_object: Any,
    vis_params: Optional[Dict] = None,
) -> str:
    """Get an XYZ tile URL for an Earth Engine object (legacy method).

    This method uses the older API that returns a different URL format.

    Args:
        ee_object: An Earth Engine Image or ImageCollection.
        vis_params: Visualization parameters dictionary.
            Supports matplotlib colormap names as palette (e.g., "terrain", "viridis").

    Returns:
        XYZ tile URL string.
    """
    if ee is None:
        raise ImportError(
            "The 'ee' module is not installed. Please install earthengine-api."
        )

    # Process vis_params to handle matplotlib colormaps
    vis_params = process_vis_params(vis_params)

    # Handle ImageCollection by taking the mosaic
    if isinstance(ee_object, ee.ImageCollection):
        ee_object = ee_object.mosaic()

    # Get the map ID
    map_id_dict = ee_object.getMapId(vis_params)

    # Extract the tile URL
    # Different EE API versions may return different structures
    if "tile_fetcher" in map_id_dict:
        tile_url = map_id_dict["tile_fetcher"].url_format
    else:
        # Fallback for older API versions
        mapid = map_id_dict.get("mapid", "")
        token = map_id_dict.get("token", "")
        tile_url = f"https://earthengine.googleapis.com/v1alpha/{mapid}/tiles/{{z}}/{{x}}/{{y}}"
        if token:
            tile_url += f"?token={token}"

    return tile_url


def ee_to_qgis_layer(
    ee_object: Any,
    vis_params: Optional[Dict] = None,
    name: str = "EE Layer",
) -> QgsRasterLayer:
    """Convert an Earth Engine Image to a QGIS raster layer.

    Args:
        ee_object: An Earth Engine Image or ImageCollection.
        vis_params: Visualization parameters dictionary.
        name: Name for the layer.

    Returns:
        QgsRasterLayer instance.
    """
    tile_url = get_ee_tile_url(ee_object, vis_params)

    # Create XYZ tile layer
    # Format the URL for QGIS (uses {z}, {x}, {y} instead of {Z}, {X}, {Y})
    # QGIS expects: type=xyz&url=...
    uri = f"type=xyz&url={tile_url}&zmax=24&zmin=0"

    layer = QgsRasterLayer(uri, name, "wms")

    if not layer.isValid():
        raise ValueError(f"Failed to create valid layer: {name}")

    return layer


def _ee_geometry_to_qgis(geometry_info: Dict) -> Optional[QgsGeometry]:
    """Convert Earth Engine geometry info to QgsGeometry.

    Args:
        geometry_info: Dictionary from ee.Geometry.getInfo().

    Returns:
        QgsGeometry or None if conversion fails.
    """
    geom_type = geometry_info.get("type", "").lower()
    coordinates = geometry_info.get("coordinates", [])

    if geom_type == "point":
        if len(coordinates) >= 2:
            return QgsGeometry.fromPointXY(QgsPointXY(coordinates[0], coordinates[1]))

    elif geom_type == "multipoint":
        points = [QgsPointXY(c[0], c[1]) for c in coordinates if len(c) >= 2]
        if points:
            return QgsGeometry.fromMultiPointXY(points)

    elif geom_type == "linestring":
        points = [QgsPointXY(c[0], c[1]) for c in coordinates if len(c) >= 2]
        if len(points) >= 2:
            return QgsGeometry.fromPolylineXY(points)

    elif geom_type == "multilinestring":
        lines = []
        for line_coords in coordinates:
            points = [QgsPointXY(c[0], c[1]) for c in line_coords if len(c) >= 2]
            if len(points) >= 2:
                lines.append(points)
        if lines:
            return QgsGeometry.fromMultiPolylineXY(lines)

    elif geom_type == "polygon":
        rings = []
        for ring_coords in coordinates:
            points = [QgsPointXY(c[0], c[1]) for c in ring_coords if len(c) >= 2]
            if len(points) >= 3:
                rings.append(points)
        if rings:
            return QgsGeometry.fromPolygonXY(rings)

    elif geom_type == "multipolygon":
        polygons = []
        for poly_coords in coordinates:
            rings = []
            for ring_coords in poly_coords:
                points = [QgsPointXY(c[0], c[1]) for c in ring_coords if len(c) >= 2]
                if len(points) >= 3:
                    rings.append(points)
            if rings:
                polygons.append(rings)
        if polygons:
            return QgsGeometry.fromMultiPolygonXY(polygons)

    elif geom_type == "geometrycollection":
        # Handle geometry collections by returning the first valid geometry
        geometries = geometry_info.get("geometries", [])
        for geom in geometries:
            result = _ee_geometry_to_qgis(geom)
            if result:
                return result

    return None


def _get_qgis_wkb_type(geometry_type: str) -> QgsWkbTypes:
    """Get QGIS WKB type from geometry type string."""
    type_map = {
        "point": QgsWkbTypes.Point,
        "multipoint": QgsWkbTypes.MultiPoint,
        "linestring": QgsWkbTypes.LineString,
        "multilinestring": QgsWkbTypes.MultiLineString,
        "polygon": QgsWkbTypes.Polygon,
        "multipolygon": QgsWkbTypes.MultiPolygon,
    }
    return type_map.get(geometry_type.lower(), QgsWkbTypes.Unknown)


def _python_type_to_qvariant(value: Any) -> QVariant:
    """Convert Python type to QVariant type for field definition."""
    if isinstance(value, bool):
        return QVariant.Bool
    elif isinstance(value, int):
        return QVariant.Int
    elif isinstance(value, float):
        return QVariant.Double
    elif isinstance(value, str):
        return QVariant.String
    elif isinstance(value, (list, dict)):
        return QVariant.String  # Store as JSON string
    else:
        return QVariant.String


class FeatureCollectionLoaderWorker(QThread):
    """Worker thread for loading FeatureCollection data from Earth Engine."""

    finished = pyqtSignal(object)  # fc_info dict
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, fc, max_features: int = 5000):
        super().__init__()
        self.fc = fc
        self.max_features = max_features

    def run(self):
        """Fetch the FeatureCollection data."""
        try:
            self.progress.emit("Fetching features from Earth Engine...")
            fc_limited = self.fc.limit(self.max_features)
            fc_info = fc_limited.getInfo()
            self.finished.emit(fc_info)
        except Exception as e:
            self.error.emit(str(e))


def ee_feature_collection_to_vector(
    fc: Any,
    name: str = "EE FeatureCollection",
    max_features: int = 5000,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> QgsVectorLayer:
    """Convert an Earth Engine FeatureCollection to a QGIS vector layer.

    Args:
        fc: Earth Engine FeatureCollection.
        name: Name for the layer.
        max_features: Maximum number of features to fetch.
        progress_callback: Optional callback for progress updates.

    Returns:
        QgsVectorLayer instance.
    """
    if ee is None:
        raise ImportError(
            "The 'ee' module is not installed. Please install earthengine-api."
        )

    if progress_callback:
        progress_callback("Fetching features from Earth Engine...")

    # Get the feature collection info
    # Limit the number of features to avoid memory issues
    fc_limited = fc.limit(max_features)
    fc_info = fc_limited.getInfo()

    if not fc_info or "features" not in fc_info:
        raise ValueError("Failed to get FeatureCollection info from Earth Engine")

    features_list = fc_info.get("features", [])

    if not features_list:
        raise ValueError("FeatureCollection is empty")

    if progress_callback:
        progress_callback(f"Processing {len(features_list)} features...")

    # Collect geometry types from all features to determine the best type
    geom_types = set()
    for feature_info in features_list:
        geom = feature_info.get("geometry", {})
        if geom:
            geom_types.add(geom.get("type", "").lower())

    # Determine the primary geometry type (prefer multi types for mixed)
    if "multipolygon" in geom_types or (
        "polygon" in geom_types and len(geom_types) > 1
    ):
        primary_type = "multipolygon"
    elif "polygon" in geom_types:
        primary_type = "polygon"
    elif "multilinestring" in geom_types or (
        "linestring" in geom_types and len(geom_types) > 1
    ):
        primary_type = "multilinestring"
    elif "linestring" in geom_types:
        primary_type = "linestring"
    elif "multipoint" in geom_types or ("point" in geom_types and len(geom_types) > 1):
        primary_type = "multipoint"
    else:
        primary_type = "point"

    wkb_type = _get_qgis_wkb_type(primary_type)

    # Create memory layer
    type_str = {
        QgsWkbTypes.Point: "Point",
        QgsWkbTypes.MultiPoint: "MultiPoint",
        QgsWkbTypes.LineString: "LineString",
        QgsWkbTypes.MultiLineString: "MultiLineString",
        QgsWkbTypes.Polygon: "Polygon",
        QgsWkbTypes.MultiPolygon: "MultiPolygon",
    }.get(wkb_type, "Polygon")

    layer = QgsVectorLayer(f"{type_str}?crs=EPSG:4326", name, "memory")
    provider = layer.dataProvider()

    # Collect all property keys from all features
    all_properties = set()
    property_types = {}

    for feature_info in features_list:
        props = feature_info.get("properties", {}) or {}
        for key, value in props.items():
            all_properties.add(key)
            if key not in property_types and value is not None:
                property_types[key] = _python_type_to_qvariant(value)

    # Create fields
    fields = QgsFields()
    for prop_name in sorted(all_properties):
        field_type = property_types.get(prop_name, QVariant.String)
        fields.append(QgsField(prop_name, field_type))

    provider.addAttributes(fields)
    layer.updateFields()

    if progress_callback:
        progress_callback("Converting geometries...")

    # Add features - process ALL features
    qgis_features = []
    total_features = len(features_list)

    for idx, feature_info in enumerate(features_list):
        geom_info = feature_info.get("geometry")
        props = feature_info.get("properties", {}) or {}

        if geom_info:
            qgis_geom = _ee_geometry_to_qgis(geom_info)
            if qgis_geom:
                # Handle geometry type conversion if needed
                geom_type = geom_info.get("type", "").lower()

                # Convert single geometries to multi if layer expects multi
                if primary_type == "multipolygon" and geom_type == "polygon":
                    qgis_geom = QgsGeometry.fromMultiPolygonXY([qgis_geom.asPolygon()])
                elif primary_type == "multilinestring" and geom_type == "linestring":
                    qgis_geom = QgsGeometry.fromMultiPolylineXY(
                        [qgis_geom.asPolyline()]
                    )
                elif primary_type == "multipoint" and geom_type == "point":
                    qgis_geom = QgsGeometry.fromMultiPointXY([qgis_geom.asPoint()])

                feat = QgsFeature(layer.fields())
                feat.setGeometry(qgis_geom)

                # Set attributes
                for i, field in enumerate(layer.fields()):
                    value = props.get(field.name())
                    if isinstance(value, (list, dict)):
                        value = json.dumps(value)
                    feat.setAttribute(i, value)

                qgis_features.append(feat)

        # Update progress periodically
        if progress_callback and (idx + 1) % 100 == 0:
            progress_callback(f"Processed {idx + 1}/{total_features} features...")

    if progress_callback:
        progress_callback(f"Adding {len(qgis_features)} features to layer...")

    provider.addFeatures(qgis_features)
    layer.updateExtents()

    if progress_callback:
        progress_callback(f"Loaded {len(qgis_features)} features")

    return layer


def ee_geometry_to_vector(
    geometry: Any,
    name: str = "EE Geometry",
) -> QgsVectorLayer:
    """Convert an Earth Engine Geometry to a QGIS vector layer.

    Args:
        geometry: Earth Engine Geometry.
        name: Name for the layer.

    Returns:
        QgsVectorLayer instance.
    """
    if ee is None:
        raise ImportError(
            "The 'ee' module is not installed. Please install earthengine-api."
        )

    geom_info = geometry.getInfo()
    geom_type = geom_info.get("type", "Point").lower()
    wkb_type = _get_qgis_wkb_type(geom_type)

    type_str = {
        QgsWkbTypes.Point: "Point",
        QgsWkbTypes.MultiPoint: "MultiPoint",
        QgsWkbTypes.LineString: "LineString",
        QgsWkbTypes.MultiLineString: "MultiLineString",
        QgsWkbTypes.Polygon: "Polygon",
        QgsWkbTypes.MultiPolygon: "MultiPolygon",
    }.get(wkb_type, "Polygon")

    layer = QgsVectorLayer(f"{type_str}?crs=EPSG:4326", name, "memory")
    provider = layer.dataProvider()

    qgis_geom = _ee_geometry_to_qgis(geom_info)
    if qgis_geom:
        feat = QgsFeature()
        feat.setGeometry(qgis_geom)
        provider.addFeatures([feat])
        layer.updateExtents()

    return layer
