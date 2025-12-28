"""
Earth Engine to QGIS Layer Conversion Utilities

This module provides functions to convert Earth Engine objects to QGIS layers.
"""

import json
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import ee
except ImportError:
    ee = None

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
)
from qgis.PyQt.QtCore import QVariant


def initialize_ee(project: str = None, credentials: Any = None) -> bool:
    """Initialize Earth Engine.

    Args:
        project: Google Cloud project ID.
        credentials: Optional credentials object.

    Returns:
        True if initialization was successful, False otherwise.
    """
    if ee is None:
        raise ImportError(
            "The 'ee' module is not installed. Please install earthengine-api."
        )

    try:
        if project:
            ee.Initialize(credentials=credentials, project=project)
        else:
            ee.Initialize(credentials=credentials)
        return True
    except Exception as e:
        # Try to authenticate first
        try:
            ee.Authenticate()
            if project:
                ee.Initialize(credentials=credentials, project=project)
            else:
                ee.Initialize(credentials=credentials)
            return True
        except Exception as auth_e:
            raise RuntimeError(
                f"Failed to initialize Earth Engine: {e}\n"
                f"Authentication also failed: {auth_e}"
            )


def get_ee_tile_url(
    ee_object: Any,
    vis_params: Optional[Dict] = None,
) -> str:
    """Get an XYZ tile URL for an Earth Engine object.

    Args:
        ee_object: An Earth Engine Image or ImageCollection.
        vis_params: Visualization parameters dictionary.

    Returns:
        XYZ tile URL string.
    """
    if ee is None:
        raise ImportError(
            "The 'ee' module is not installed. Please install earthengine-api."
        )

    vis_params = vis_params or {}

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

    Returns:
        XYZ tile URL string.
    """
    if ee is None:
        raise ImportError(
            "The 'ee' module is not installed. Please install earthengine-api."
        )

    vis_params = vis_params or {}

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


def ee_feature_collection_to_vector(
    fc: Any,
    name: str = "EE FeatureCollection",
    max_features: int = 5000,
) -> QgsVectorLayer:
    """Convert an Earth Engine FeatureCollection to a QGIS vector layer.

    Args:
        fc: Earth Engine FeatureCollection.
        name: Name for the layer.
        max_features: Maximum number of features to fetch.

    Returns:
        QgsVectorLayer instance.
    """
    if ee is None:
        raise ImportError(
            "The 'ee' module is not installed. Please install earthengine-api."
        )

    # Get the feature collection info
    # Limit the number of features to avoid memory issues
    fc_limited = fc.limit(max_features)
    fc_info = fc_limited.getInfo()

    if not fc_info or "features" not in fc_info:
        raise ValueError("Failed to get FeatureCollection info from Earth Engine")

    features_list = fc_info.get("features", [])

    if not features_list:
        raise ValueError("FeatureCollection is empty")

    # Determine geometry type from first feature
    first_geom = features_list[0].get("geometry", {})
    geom_type = first_geom.get("type", "Point").lower()
    wkb_type = _get_qgis_wkb_type(geom_type)

    # Create memory layer
    type_str = {
        QgsWkbTypes.Point: "Point",
        QgsWkbTypes.MultiPoint: "MultiPoint",
        QgsWkbTypes.LineString: "LineString",
        QgsWkbTypes.MultiLineString: "MultiLineString",
        QgsWkbTypes.Polygon: "Polygon",
        QgsWkbTypes.MultiPolygon: "MultiPolygon",
    }.get(wkb_type, "Point")

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

    # Add features
    qgis_features = []
    for feature_info in features_list:
        geom_info = feature_info.get("geometry")
        props = feature_info.get("properties", {}) or {}

        if geom_info:
            qgis_geom = _ee_geometry_to_qgis(geom_info)
            if qgis_geom:
                feat = QgsFeature(layer.fields())
                feat.setGeometry(qgis_geom)

                # Set attributes
                for i, field in enumerate(layer.fields()):
                    value = props.get(field.name())
                    if isinstance(value, (list, dict)):
                        value = json.dumps(value)
                    feat.setAttribute(i, value)

                qgis_features.append(feat)

    provider.addFeatures(qgis_features)
    layer.updateExtents()

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
