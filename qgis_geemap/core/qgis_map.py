"""
QGIS Map Class for Geemap

This module provides a Map class that mimics the geemap.Map interface
but operates on the QGIS map canvas instead of ipyleaflet/folium.
"""

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
    QgsCoordinateTransform,
    QgsPointXY,
    QgsRectangle,
    QgsMapLayer,
)
from qgis.utils import iface
from qgis.PyQt.QtCore import QObject, pyqtSignal

from .ee_layer import (
    ee_to_qgis_layer,
    ee_feature_collection_to_vector,
    ee_geometry_to_vector,
    get_ee_tile_url,
)


class Map(QObject):
    """A Map class that integrates geemap functionality with QGIS.

    This class provides a familiar geemap.Map-like interface for working
    with Earth Engine data in QGIS. It wraps the QGIS map canvas and
    provides methods for adding layers, setting the view, and more.

    Example:
        >>> import ee
        >>> from qgis_geemap.core import Map
        >>>
        >>> m = Map(center=(40, -100), zoom=4)
        >>> dem = ee.Image("USGS/SRTMGL1_003")
        >>> m.add_layer(dem, {"min": 0, "max": 4000}, "SRTM DEM")
    """

    layer_added = pyqtSignal(object, str)  # layer, name
    center_changed = pyqtSignal(float, float)  # lat, lon

    def __init__(
        self,
        center: Tuple[float, float] = (0, 0),
        zoom: int = 2,
        **kwargs,
    ):
        """Initialize the Map.

        Args:
            center: Tuple of (latitude, longitude) for initial center.
            zoom: Initial zoom level (0-24).
            **kwargs: Additional keyword arguments (for compatibility).
        """
        super().__init__()

        self._center = center
        self._zoom = zoom
        self._layers = {}  # name -> layer mapping
        self._ee_layers = {}  # name -> (ee_object, vis_params) mapping

        # Get the QGIS interface
        self._iface = iface
        self._canvas = self._iface.mapCanvas() if self._iface else None
        self._project = QgsProject.instance()

        # Set initial view
        if self._canvas:
            self.set_center(center[0], center[1], zoom)

    @property
    def center(self) -> Tuple[float, float]:
        """Get the current map center as (lat, lon)."""
        if self._canvas:
            center = self._canvas.center()
            # Transform from map CRS to EPSG:4326
            src_crs = self._canvas.mapSettings().destinationCrs()
            dst_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            transform = QgsCoordinateTransform(src_crs, dst_crs, self._project)
            center_4326 = transform.transform(center)
            return (center_4326.y(), center_4326.x())
        return self._center

    @center.setter
    def center(self, value: Tuple[float, float]):
        """Set the map center."""
        self.set_center(value[0], value[1])

    @property
    def zoom(self) -> int:
        """Get the current zoom level (approximate)."""
        if self._canvas:
            scale = self._canvas.scale()
            # Approximate zoom level from scale
            # Based on Web Mercator tile scales
            zoom = int(round(29.14 - 1.44 * (scale / 1000000.0) ** 0.5))
            return max(0, min(24, zoom))
        return self._zoom

    @zoom.setter
    def zoom(self, value: int):
        """Set the zoom level."""
        if self._canvas:
            # Convert zoom to scale (approximate)
            # Based on Web Mercator tile scales at equator
            scales = {
                0: 559082264,
                1: 279541132,
                2: 139770566,
                3: 69885283,
                4: 34942642,
                5: 17471321,
                6: 8735660,
                7: 4367830,
                8: 2183915,
                9: 1091958,
                10: 545979,
                11: 272989,
                12: 136495,
                13: 68247,
                14: 34124,
                15: 17062,
                16: 8531,
                17: 4265,
                18: 2133,
                19: 1066,
                20: 533,
                21: 267,
                22: 133,
                23: 67,
                24: 33,
            }
            value = max(0, min(24, value))
            scale = scales.get(value, 545979)
            self._canvas.zoomScale(scale)
            self._zoom = value

    @property
    def bounds(self) -> List[List[float]]:
        """Get the current map bounds as [[south, west], [north, east]]."""
        if self._canvas:
            extent = self._canvas.extent()
            src_crs = self._canvas.mapSettings().destinationCrs()
            dst_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            transform = QgsCoordinateTransform(src_crs, dst_crs, self._project)
            extent_4326 = transform.transformBoundingBox(extent)
            return [
                [extent_4326.yMinimum(), extent_4326.xMinimum()],
                [extent_4326.yMaximum(), extent_4326.xMaximum()],
            ]
        return [[-90, -180], [90, 180]]

    def set_center(self, lat: float, lon: float, zoom: Optional[int] = None):
        """Set the map center to the given coordinates.

        Args:
            lat: Latitude.
            lon: Longitude.
            zoom: Optional zoom level.
        """
        if self._canvas:
            # Create point in EPSG:4326
            point_4326 = QgsPointXY(lon, lat)

            # Transform to map CRS
            src_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            dst_crs = self._canvas.mapSettings().destinationCrs()
            transform = QgsCoordinateTransform(src_crs, dst_crs, self._project)
            point_map = transform.transform(point_4326)

            # Set center
            self._canvas.setCenter(point_map)

            # Set zoom if provided
            if zoom is not None:
                self.zoom = zoom

            self._canvas.refresh()
            self._center = (lat, lon)
            self.center_changed.emit(lat, lon)

    def center_object(
        self,
        ee_object: Any,
        zoom: Optional[int] = None,
    ):
        """Center the map on an Earth Engine object.

        Args:
            ee_object: An Earth Engine object (Image, FeatureCollection, Geometry, Feature).
            zoom: Optional zoom level.
        """
        if ee is None:
            raise ImportError("Earth Engine API not available")

        if not self._canvas:
            return

        # Get the geometry/bounds from the EE object
        if isinstance(ee_object, ee.Image):
            geom = ee_object.geometry()
        elif isinstance(ee_object, ee.Feature):
            geom = ee_object.geometry()
        elif isinstance(ee_object, ee.FeatureCollection):
            geom = ee_object.geometry()
        elif isinstance(ee_object, ee.Geometry):
            geom = ee_object
        else:
            # Try to get bounds anyway
            try:
                geom = ee_object.geometry()
            except Exception:
                raise ValueError(
                    f"Cannot get geometry from object of type {type(ee_object)}"
                )

        # Get bounds
        bounds = geom.bounds().getInfo()
        coords = bounds.get("coordinates", [[]])[0]

        if len(coords) >= 4:
            # coords is [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax], [xmin, ymin]]
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]

            xmin, xmax = min(lons), max(lons)
            ymin, ymax = min(lats), max(lats)

            # Create extent in EPSG:4326
            extent_4326 = QgsRectangle(xmin, ymin, xmax, ymax)

            # Transform to map CRS
            src_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            dst_crs = self._canvas.mapSettings().destinationCrs()
            transform = QgsCoordinateTransform(src_crs, dst_crs, self._project)
            extent_map = transform.transformBoundingBox(extent_4326)

            # Set extent with some padding
            extent_map.scale(1.1)
            self._canvas.setExtent(extent_map)

            if zoom is not None:
                self.zoom = zoom

            self._canvas.refresh()

    def add_layer(
        self,
        ee_object: Any,
        vis_params: Optional[Dict] = None,
        name: Optional[str] = None,
        shown: bool = True,
        opacity: float = 1.0,
    ) -> QgsMapLayer:
        """Add an Earth Engine layer to the map.

        Args:
            ee_object: An Earth Engine Image, ImageCollection, FeatureCollection, or Geometry.
            vis_params: Visualization parameters dictionary.
            name: Layer name (auto-generated if not provided).
            shown: Whether the layer should be visible.
            opacity: Layer opacity (0.0 to 1.0).

        Returns:
            The QGIS layer that was added.
        """
        if ee is None:
            raise ImportError("Earth Engine API not available")

        vis_params = vis_params or {}

        # Generate layer name if not provided
        if name is None:
            existing_names = list(self._layers.keys())
            base_name = "EE Layer"
            counter = 1
            name = base_name
            while name in existing_names:
                name = f"{base_name} {counter}"
                counter += 1

        # Remove existing layer with same name
        if name in self._layers:
            self.remove_layer(name)

        # Determine the type of EE object and create appropriate layer
        layer = None

        if isinstance(ee_object, (ee.Image, ee.ImageCollection)):
            # Create raster layer from XYZ tiles
            layer = ee_to_qgis_layer(ee_object, vis_params, name)

        elif isinstance(ee_object, ee.FeatureCollection):
            # Check if we should render as vector or raster
            # If vis_params contains color/fillColor/etc, try vector
            # Otherwise, render as tiles
            use_vector = vis_params.get("as_vector", False)

            if use_vector:
                layer = ee_feature_collection_to_vector(ee_object, name)
            else:
                # Render FeatureCollection as styled image tiles
                # Apply default styling if not provided
                styled_fc = ee_object
                if vis_params:
                    styled_fc = ee_object.style(**vis_params)
                layer = ee_to_qgis_layer(styled_fc, {}, name)

        elif isinstance(ee_object, ee.Feature):
            # Convert single feature to FeatureCollection
            fc = ee.FeatureCollection([ee_object])
            layer = ee_feature_collection_to_vector(fc, name)

        elif isinstance(ee_object, ee.Geometry):
            layer = ee_geometry_to_vector(ee_object, name)

        else:
            raise TypeError(
                f"Unsupported Earth Engine object type: {type(ee_object)}. "
                "Expected Image, ImageCollection, FeatureCollection, Feature, or Geometry."
            )

        if layer and layer.isValid():
            # Set opacity
            if isinstance(layer, QgsRasterLayer):
                layer.renderer().setOpacity(opacity)
            else:
                layer.setOpacity(opacity)

            # Add to project
            self._project.addMapLayer(layer, True)

            # Set visibility
            layer_tree = self._project.layerTreeRoot().findLayer(layer.id())
            if layer_tree:
                layer_tree.setItemVisibilityChecked(shown)

            # Store references
            self._layers[name] = layer
            self._ee_layers[name] = (ee_object, vis_params)

            # Refresh canvas
            if self._canvas:
                self._canvas.refresh()

            self.layer_added.emit(layer, name)

            return layer
        else:
            raise ValueError(f"Failed to create valid layer: {name}")

    def addLayer(
        self,
        ee_object: Any,
        vis_params: Optional[Dict] = None,
        name: Optional[str] = None,
        shown: bool = True,
        opacity: float = 1.0,
    ) -> QgsMapLayer:
        """Alias for add_layer (for compatibility with geemap API)."""
        return self.add_layer(ee_object, vis_params, name, shown, opacity)

    def remove_layer(self, name: str) -> bool:
        """Remove a layer from the map by name.

        Args:
            name: Name of the layer to remove.

        Returns:
            True if layer was removed, False if not found.
        """
        if name in self._layers:
            layer = self._layers[name]
            self._project.removeMapLayer(layer.id())
            del self._layers[name]
            if name in self._ee_layers:
                del self._ee_layers[name]
            return True
        return False

    def clear_layers(self):
        """Remove all Earth Engine layers added through this Map instance."""
        for name in list(self._layers.keys()):
            self.remove_layer(name)

    def get_layer(self, name: str) -> Optional[QgsMapLayer]:
        """Get a layer by name.

        Args:
            name: Name of the layer.

        Returns:
            The QGIS layer or None if not found.
        """
        return self._layers.get(name)

    def get_layer_names(self) -> List[str]:
        """Get list of layer names added through this Map instance."""
        return list(self._layers.keys())

    def set_options(self, **kwargs):
        """Set map options (for compatibility with geemap API).

        Currently supported options:
            - basemap: Name of basemap to use
        """
        basemap = kwargs.get("basemap")
        if basemap:
            self.add_basemap(basemap)

    def add_basemap(self, basemap: str = "ROADMAP", **kwargs):
        """Add a basemap layer.

        Args:
            basemap: Name of the basemap. Options include:
                - "ROADMAP" or "Google Maps"
                - "SATELLITE" or "Google Satellite"
                - "TERRAIN" or "Google Terrain"
                - "HYBRID" or "Google Satellite Hybrid"
                - "OpenStreetMap"
                - "CartoDB Positron"
                - "CartoDB Dark Matter"
                - "Esri World Imagery"
        """
        basemap_urls = {
            "ROADMAP": "https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
            "Google Maps": "https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
            "SATELLITE": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
            "Google Satellite": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
            "TERRAIN": "https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}",
            "Google Terrain": "https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}",
            "HYBRID": "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            "Google Satellite Hybrid": "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            "OpenStreetMap": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            "CartoDB Positron": "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
            "CartoDB Dark Matter": "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
            "Esri World Imagery": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        }

        url = basemap_urls.get(basemap)
        if not url:
            available = ", ".join(basemap_urls.keys())
            raise ValueError(
                f"Unknown basemap: {basemap}. Available options: {available}"
            )

        uri = f"type=xyz&url={url}&zmax=19&zmin=0"
        layer = QgsRasterLayer(uri, basemap, "wms")

        if layer.isValid():
            self._project.addMapLayer(layer, True)

            # Move to bottom of layer tree
            root = self._project.layerTreeRoot()
            layer_node = root.findLayer(layer.id())
            if layer_node:
                clone = layer_node.clone()
                root.insertChildNode(-1, clone)
                root.removeChildNode(layer_node)

            self._layers[basemap] = layer
            if self._canvas:
                self._canvas.refresh()
        else:
            raise ValueError(f"Failed to create basemap layer: {basemap}")

    def add_ee_layer(
        self,
        ee_object: Any,
        vis_params: Optional[Dict] = None,
        name: Optional[str] = None,
        shown: bool = True,
        opacity: float = 1.0,
    ) -> QgsMapLayer:
        """Alias for add_layer (for compatibility with some geemap code)."""
        return self.add_layer(ee_object, vis_params, name, shown, opacity)

    def zoom_to_bounds(self, bounds: List[List[float]]):
        """Zoom to the specified bounds.

        Args:
            bounds: Bounds as [[south, west], [north, east]].
        """
        if self._canvas and len(bounds) == 2:
            south, west = bounds[0]
            north, east = bounds[1]

            # Create extent in EPSG:4326
            extent_4326 = QgsRectangle(west, south, east, north)

            # Transform to map CRS
            src_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            dst_crs = self._canvas.mapSettings().destinationCrs()
            transform = QgsCoordinateTransform(src_crs, dst_crs, self._project)
            extent_map = transform.transformBoundingBox(extent_4326)

            self._canvas.setExtent(extent_map)
            self._canvas.refresh()

    def zoom_to_layer(self, name: str):
        """Zoom to the extent of a layer.

        Args:
            name: Name of the layer to zoom to.
        """
        if name in self._layers and self._canvas:
            layer = self._layers[name]
            extent = layer.extent()
            self._canvas.setExtent(extent)
            self._canvas.zoomByFactor(1.1)  # Add some padding
            self._canvas.refresh()

    def __repr__(self) -> str:
        """Return string representation of the Map."""
        return (
            f"Map(center={self.center}, zoom={self.zoom}, "
            f"layers={len(self._layers)})"
        )


# For convenience, allow importing Map directly from geemap in QGIS context
# This patches the geemap module if it's available
def patch_geemap():
    """Patch geemap.Map to use the QGIS Map class."""
    try:
        import geemap

        # Store original Map class
        if not hasattr(geemap, "_OriginalMap"):
            geemap._OriginalMap = geemap.Map

        # Replace with QGIS Map
        geemap.Map = Map
        return True
    except ImportError:
        return False
