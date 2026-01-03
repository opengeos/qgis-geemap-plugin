# QGIS Geemap Plugin

A QGIS plugin that integrates [geemap](https://geemap.org) for working with Google Earth Engine data directly in QGIS.

[![QGIS Plugin](https://img.shields.io/badge/QGIS-Plugin-green.svg)](https://plugins.qgis.org/plugins/qgis_geemap)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- **Earth Engine Image Layers**: Add Earth Engine Image and ImageCollection layers as XYZ tile layers
- **FeatureCollection Support**: Add Earth Engine FeatureCollections as vector layers or styled raster tiles
- **Familiar geemap API**: Use the familiar `geemap.Map()` API directly in the QGIS Python console
- **Interactive Panel**: GUI panel for adding layers, running code, and managing basemaps
- **Settings Panel**: Configure Earth Engine authentication and plugin options
- **Update Checker**: Check for and install plugin updates from GitHub

## Video Tutorial

👉 [QGIS Geemap Plugin: Running Google Earth Engine and Jupyter Notebook within QGIS](https://youtu.be/QHFp0v579Hc)

[![QGIS Geemap Plugin](https://github.com/user-attachments/assets/5907407b-27da-4b07-8bf1-6d245cfc6aec)](https://youtu.be/QHFp0v579Hc)

## Installation

### Prerequisites

1. **QGIS 3.28 or higher**
2. **Google Earth Engine Account**: Sign up at [earthengine.google.com](https://earthengine.google.com/)

### Install QGIS and Google Earth Engine

#### 1) Install Pixi

#### Linux/macOS (bash/zsh)

```bash
curl -fsSL https://pixi.sh/install.sh | sh
```

Close and re-open your terminal (or reload your shell) so `pixi` is on your `PATH`. Then confirm:

```bash
pixi --version
```

#### Windows (PowerShell)

Open **PowerShell** (preferably as a normal user, Admin not required), then run:

```powershell
powershell -ExecutionPolicy Bypass -c "irm -useb https://pixi.sh/install.ps1 | iex"
```

Close and re-open PowerShell, then confirm:

```powershell
pixi --version
```

---

#### 2) Create a Pixi project

Navigate to a directory where you want to create the project and run:

```bash
pixi init geo
cd geo
```

#### 3) Install the environment

From the `geo` folder:

```bash
pixi add qgis geemap
```

#### 4) Authenticate Earth Engine

```bash
pixi run earthengine authenticate
```

### Installing the Plugin

#### Method 1: From QGIS Plugin Manager (Recommended)

1. Open QGIS using `pixi run qgis`
2. Go to **Plugins** → **Manage and Install Plugins...**
3. Go to the **Settings** tab
4. Click **Add...** under "Plugin Repositories"
5. Give a name for the repository, e.g., "OpenGeos"
6. Enter the URL of the repository: https://qgis.gishub.org/plugins.xml
7. Click **OK**
8. Go to the **All** tab
9. Search for "Geemap"
10. Select "Geemap" from the list and click **Install Plugin**

#### Method 2: From ZIP File

1. Download the latest release ZIP from <https://qgis.gishub.org>
2. In QGIS, go to `Plugins` → `Manage and Install Plugins`
3. Click `Install from ZIP` and select the downloaded file
4. Enable the plugin in the `Installed` tab

#### Method 3: Manual Installation

1. Clone or download this repository
2. Copy the `qgis_geemap` folder to your QGIS plugins directory:
   - **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Windows**: `C:\Users\<username>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\`
   - **macOS**: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
3. Restart QGIS and enable the plugin

### Uninstalling

```bash
python install.py --remove
# or
./install.sh --remove
```

## Usage

### Using the Geemap Panel

1. Open the Geemap panel from the toolbar or menu (**Geemap → Geemap Panel**)
2. Enter an Earth Engine asset ID (e.g., `USGS/SRTMGL1_003`)
3. Configure visualization parameters
4. Click "Add Image Layer"

### Using the Python Console

The plugin patches `geemap.Map` to work with QGIS. You can use familiar geemap code:

```python
import ee
import geemap

# Initialize Earth Engine (if not already done)
# ee.Initialize(project='your-project-id')

# Create a Map instance (this uses the QGIS canvas)
m = geemap.Map(center=(40, -100), zoom=4)

# Add an Earth Engine Image
dem = ee.Image("USGS/SRTMGL1_003")
vis_params = {
    "min": 0,
    "max": 4000,
    "palette": ["006633", "E5FFCC", "662A00", "D8D8D8", "F5F5F5"],
}
m.add_layer(dem, vis_params, "SRTM DEM")

# Add a FeatureCollection
states = ee.FeatureCollection("TIGER/2018/States")
m.add_layer(states, {}, "US States")

# Center on an object
m.center_object(states, zoom=4)
```

### Alternative: Direct Import

You can also import the Map class directly from the plugin:

```python
import ee
from qgis_geemap.core import Map

# ee.Initialize(project='your-project-id')

m = Map(center=(40, -100), zoom=4)
dem = ee.Image("USGS/SRTMGL1_003")
m.add_layer(dem, {"min": 0, "max": 4000}, "DEM")
```

## API Reference

### Map Class

The `Map` class provides a QGIS-compatible interface similar to `geemap.Map`:

#### Constructor

```python
Map(center=(lat, lon), zoom=level)
```

#### Properties

- `center`: Get/set map center as `(lat, lon)` tuple
- `zoom`: Get/set zoom level (0-24)
- `bounds`: Get current bounds as `[[south, west], [north, east]]`

#### Methods

- `add_layer(ee_object, vis_params=None, name=None, shown=True, opacity=1.0)`: Add an Earth Engine layer
- `remove_layer(name)`: Remove a layer by name
- `clear_layers()`: Remove all Earth Engine layers
- `set_center(lat, lon, zoom=None)`: Set the map center
- `center_object(ee_object, zoom=None)`: Center the map on an Earth Engine object
- `add_basemap(name)`: Add a basemap layer
- `zoom_to_bounds(bounds)`: Zoom to specified bounds
- `zoom_to_layer(name)`: Zoom to a layer's extent

#### Supported Earth Engine Objects

- `ee.Image`: Rendered as XYZ tile layers
- `ee.ImageCollection`: Mosaicked and rendered as XYZ tiles
- `ee.FeatureCollection`: Rendered as styled tiles or vector layers
- `ee.Feature`: Converted to vector layer
- `ee.Geometry`: Converted to vector layer

## Packaging for Distribution

To create a zip file for distribution or upload to the QGIS plugin repository:

```bash
python package_plugin.py
```

Or using shell script:

```bash
./package_plugin.sh
```

This creates a `qgis_geemap-{version}.zip` file ready for distribution.

## Development

### Project Structure

```
qgis-geemap-plugin/
├── qgis_geemap/              # Main plugin directory
│   ├── __init__.py           # Plugin entry point
│   ├── qgis_geemap.py        # Main plugin class
│   ├── metadata.txt          # Plugin metadata
│   ├── LICENSE               # MIT License
│   ├── core/                 # Core functionality
│   │   ├── __init__.py
│   │   ├── qgis_map.py       # Map class implementation
│   │   └── ee_layer.py       # EE to QGIS layer conversion
│   ├── dialogs/              # UI dialogs and panels
│   │   ├── __init__.py
│   │   ├── geemap_dock.py    # Main geemap panel
│   │   ├── settings_dock.py  # Settings panel
│   │   └── update_checker.py # Update checker dialog
│   └── icons/                # Plugin icons
│       ├── icon.svg
│       ├── settings.svg
│       ├── about.svg
│       └── earth.svg
├── install.py                # Python installation script
├── install.sh                # Shell installation script
├── package_plugin.py         # Python packaging script
├── package_plugin.sh         # Shell packaging script
├── LICENSE                   # MIT License
└── README.md                 # This file
```

## Troubleshooting

### Earth Engine not initialized

Make sure you have authenticated with Earth Engine:

```bash
earthengine authenticate
```

Then initialize in Python:

```python
import ee
ee.Initialize(project='your-project-id')
```

### Module not found errors

Ensure earthengine-api is installed in the QGIS Python environment. You may need to find QGIS's Python interpreter and install packages there:

```bash
# Find QGIS Python path (varies by OS)
# Then install:
/path/to/qgis/python -m pip install earthengine-api geemap
```

### Layers not displaying

- Check that Earth Engine is properly initialized
- Verify your Earth Engine project has the necessary APIs enabled
- Check the QGIS log for error messages

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
