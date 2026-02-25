"""Virtual Environment Manager for QGIS Geemap Plugin.

Manages an isolated Python virtual environment at ~/.qgis_geemap for
installing geemap dependencies without polluting the QGIS built-in
Python environment.
"""

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import time
from typing import Callable, Optional, Tuple

from qgis.core import Qgis, QgsMessageLog

VENV_DIR = os.path.expanduser("~/.qgis_geemap")

REQUIRED_PACKAGES = [
    ("earthengine-api", ""),
    ("geemap", ""),
    ("google-auth-oauthlib", ""),
]

DEPS_HASH_FILE = os.path.join(VENV_DIR, "deps_hash.txt")

# Bump this when install logic changes to force a reinstall
_INSTALL_LOGIC_VERSION = "1"

# Map pip package names to their importable directory names in site-packages
_PACKAGE_MARKERS = {
    "earthengine-api": "ee",
    "geemap": "geemap",
    "google-auth-oauthlib": "google_auth_oauthlib",
}

# Progress weight for each package during installation (must sum to 1.0)
_PACKAGE_WEIGHTS = {
    "earthengine-api": 0.20,
    "geemap": 0.60,
    "google-auth-oauthlib": 0.20,
}


def _log(message: str, level=Qgis.Info):
    """Log a message to the QGIS message log.

    Args:
        message: The message to log.
        level: The log level (Qgis.Info, Qgis.Warning, Qgis.Critical).
    """
    QgsMessageLog.logMessage(message, "Geemap", level)


def _compute_deps_hash() -> str:
    """Compute an MD5 hash of the current dependency specification.

    Returns:
        A hex digest string representing the current dependency state.
    """
    content = repr(REQUIRED_PACKAGES) + _INSTALL_LOGIC_VERSION
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def _read_deps_hash() -> Optional[str]:
    """Read the stored dependency hash from disk.

    Returns:
        The stored hash string, or None if the file doesn't exist.
    """
    try:
        with open(DEPS_HASH_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except (OSError, IOError):
        return None


def _write_deps_hash():
    """Write the current dependency hash to disk."""
    try:
        os.makedirs(os.path.dirname(DEPS_HASH_FILE), exist_ok=True)
        with open(DEPS_HASH_FILE, "w", encoding="utf-8") as f:
            f.write(_compute_deps_hash())
    except (OSError, IOError) as e:
        _log(f"Failed to write deps hash: {e}", Qgis.Warning)


def get_venv_site_packages(venv_dir: str = None) -> str:
    """Get the path to the venv's site-packages directory.

    Args:
        venv_dir: Path to the virtual environment. Defaults to VENV_DIR.

    Returns:
        The absolute path to the site-packages directory.
    """
    if venv_dir is None:
        venv_dir = VENV_DIR

    if platform.system() == "Windows":
        return os.path.join(venv_dir, "Lib", "site-packages")

    # Linux/macOS: scan lib/ for pythonX.Y directory
    lib_dir = os.path.join(venv_dir, "lib")
    if os.path.exists(lib_dir):
        for entry in os.listdir(lib_dir):
            if entry.startswith("python"):
                candidate = os.path.join(lib_dir, entry, "site-packages")
                if os.path.exists(candidate):
                    return candidate

    # Fallback using current Python version
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return os.path.join(venv_dir, "lib", version, "site-packages")


def get_venv_python_path(venv_dir: str = None) -> str:
    """Get the path to the venv's Python executable.

    Args:
        venv_dir: Path to the virtual environment. Defaults to VENV_DIR.

    Returns:
        The absolute path to the Python executable.
    """
    if venv_dir is None:
        venv_dir = VENV_DIR

    if platform.system() == "Windows":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python3")


def venv_exists(venv_dir: str = None) -> bool:
    """Check if the virtual environment exists and has a Python executable.

    Args:
        venv_dir: Path to the virtual environment. Defaults to VENV_DIR.

    Returns:
        True if the venv Python executable exists.
    """
    python_path = get_venv_python_path(venv_dir)
    return os.path.isfile(python_path)


def _get_clean_env() -> dict:
    """Get a clean environment dict without QGIS-specific variables.

    Removes variables that could cause the venv's Python to pick up
    QGIS's internal packages instead of the venv's own packages.

    Returns:
        A copy of os.environ with QGIS-specific variables removed.
    """
    env = os.environ.copy()
    for var in [
        "PYTHONPATH",
        "PYTHONHOME",
        "VIRTUAL_ENV",
        "QGIS_PREFIX_PATH",
        "QGIS_PLUGINPATH",
        "PROJ_DATA",
        "PROJ_LIB",
        "GDAL_DATA",
        "GDAL_DRIVER_PATH",
    ]:
        env.pop(var, None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _get_subprocess_kwargs() -> dict:
    """Get platform-specific subprocess keyword arguments.

    On Windows, hides the console window that would otherwise flash
    when running subprocess commands.

    Returns:
        A dict of keyword arguments to pass to subprocess.run/Popen.
    """
    kwargs = {}
    if platform.system() == "Windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def _quick_check_packages(venv_dir: str = None) -> Tuple[bool, str]:
    """Fast filesystem check for installed packages.

    Checks for the presence of package directories in site-packages
    without running any subprocesses.

    Args:
        venv_dir: Path to the virtual environment. Defaults to VENV_DIR.

    Returns:
        A tuple of (all_found, message).
    """
    site_packages = get_venv_site_packages(venv_dir)
    if not os.path.exists(site_packages):
        return False, "Site-packages directory not found"

    for pkg_name, marker_dir in _PACKAGE_MARKERS.items():
        pkg_path = os.path.join(site_packages, marker_dir)
        if not os.path.exists(pkg_path):
            return False, f"{pkg_name} not found"

    return True, "All packages found"


def get_venv_status() -> Tuple[bool, str]:
    """Check if the virtual environment is ready with all dependencies.

    This is a fast, filesystem-only check that is safe to call from the
    main UI thread. No subprocesses are spawned.

    Returns:
        A tuple of (is_ready, status_message).
    """
    if not os.path.isdir(VENV_DIR):
        return False, "Dependencies not installed"

    if not venv_exists():
        return False, "Dependencies not installed"

    ok, msg = _quick_check_packages()
    if not ok:
        return False, msg

    # Check if dependency specification has changed
    stored_hash = _read_deps_hash()
    current_hash = _compute_deps_hash()
    if stored_hash is not None and stored_hash != current_hash:
        return False, "Dependencies need updating"

    # If no hash file exists (first run or after upgrade), write it
    if stored_hash is None:
        _write_deps_hash()

    return True, "Ready"


def ensure_venv_packages_available() -> bool:
    """Add the venv's site-packages to sys.path if not already present.

    This must be called before any imports of venv-installed packages
    (ee, geemap, etc.) so Python can find them.

    Returns:
        True if the site-packages directory was found and added.
    """
    if not venv_exists():
        _log("Venv does not exist, cannot load packages", Qgis.Warning)
        return False

    site_packages = get_venv_site_packages()
    if not os.path.exists(site_packages):
        _log(f"Venv site-packages not found: {site_packages}", Qgis.Warning)
        return False

    if site_packages not in sys.path:
        sys.path.insert(0, site_packages)
        _log(f"Added venv site-packages to sys.path: {site_packages}")

    return True


def _cleanup_partial_venv(venv_dir: str = None):
    """Remove a partially-created virtual environment.

    Args:
        venv_dir: Path to the virtual environment. Defaults to VENV_DIR.
    """
    if venv_dir is None:
        venv_dir = VENV_DIR
    if os.path.exists(venv_dir):
        _log(f"Cleaning up partial venv: {venv_dir}", Qgis.Warning)
        shutil.rmtree(venv_dir, ignore_errors=True)


def create_venv(
    venv_dir: str = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Tuple[bool, str]:
    """Create a virtual environment using QGIS's Python.

    Args:
        venv_dir: Path for the virtual environment. Defaults to VENV_DIR.
        progress_callback: Optional callback(percent, message) for progress.

    Returns:
        A tuple of (success, message).
    """
    if venv_dir is None:
        venv_dir = VENV_DIR

    if venv_exists(venv_dir):
        _log("Venv already exists, skipping creation")
        return True, "Virtual environment already exists"

    if progress_callback:
        progress_callback(0, "Creating virtual environment...")

    # Find system Python
    system_python = sys.executable
    if platform.system() == "Windows":
        candidate = os.path.join(sys.prefix, "python.exe")
        if os.path.isfile(candidate):
            system_python = candidate

    _log(f"Creating venv at {venv_dir} using {system_python}")

    try:
        os.makedirs(os.path.dirname(venv_dir), exist_ok=True)
        result = subprocess.run(
            [system_python, "-m", "venv", venv_dir],
            capture_output=True,
            text=True,
            timeout=120,
            env=_get_clean_env(),
            **_get_subprocess_kwargs(),
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            _log(f"Venv creation failed: {error_msg}", Qgis.Critical)
            _cleanup_partial_venv(venv_dir)
            return False, f"Failed to create virtual environment:\n{error_msg}"

    except subprocess.TimeoutExpired:
        _log("Venv creation timed out", Qgis.Critical)
        _cleanup_partial_venv(venv_dir)
        return False, "Virtual environment creation timed out (120s)"
    except Exception as e:
        _log(f"Venv creation error: {e}", Qgis.Critical)
        _cleanup_partial_venv(venv_dir)
        return False, f"Failed to create virtual environment:\n{e}"

    # Verify venv was created
    if not venv_exists(venv_dir):
        _cleanup_partial_venv(venv_dir)
        return False, "Virtual environment was not created successfully"

    # Bootstrap pip if not present
    venv_python = get_venv_python_path(venv_dir)
    try:
        result = subprocess.run(
            [venv_python, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            env=_get_clean_env(),
            **_get_subprocess_kwargs(),
        )
        if result.returncode != 0:
            _log("pip not found in venv, bootstrapping with ensurepip")
            subprocess.run(
                [venv_python, "-m", "ensurepip", "--upgrade"],
                capture_output=True,
                text=True,
                timeout=120,
                env=_get_clean_env(),
                **_get_subprocess_kwargs(),
            )
    except Exception as e:
        _log(f"pip bootstrap warning: {e}", Qgis.Warning)

    if progress_callback:
        progress_callback(100, "Virtual environment created")

    _log("Venv created successfully")
    return True, "Virtual environment created"


def _run_pip_install(
    venv_dir: str,
    package_spec: str,
    extra_args: Optional[list] = None,
    timeout: int = 600,
) -> Tuple[bool, str, str]:
    """Run pip install for a single package in the venv.

    Args:
        venv_dir: Path to the virtual environment.
        package_spec: Package specification (e.g., "geemap>=0.30.0").
        extra_args: Additional pip arguments.
        timeout: Command timeout in seconds.

    Returns:
        A tuple of (success, stdout, stderr).
    """
    venv_python = get_venv_python_path(venv_dir)
    cmd = [
        venv_python,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--no-warn-script-location",
        "--disable-pip-version-check",
        "--prefer-binary",
    ]
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(package_spec)

    _log(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_get_clean_env(),
            **_get_subprocess_kwargs(),
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", f"Installation timed out after {timeout}s"
    except Exception as e:
        return False, "", str(e)


def _is_ssl_error(stderr: str) -> bool:
    """Check if the error is SSL-related."""
    lower = stderr.lower()
    return any(
        kw in lower for kw in ["ssl", "certificate", "certificate_verify_failed"]
    )


def _is_network_error(stderr: str) -> bool:
    """Check if the error is a transient network issue."""
    lower = stderr.lower()
    return any(
        kw in lower
        for kw in [
            "connection reset",
            "connection refused",
            "timed out",
            "timeout",
            "temporary failure",
            "name resolution",
            "network is unreachable",
        ]
    )


def _is_hash_error(stderr: str) -> bool:
    """Check if the error is a hash mismatch (corrupted cache)."""
    lower = stderr.lower()
    return "hash" in lower and ("mismatch" in lower or "expected" in lower)


def install_dependencies(
    venv_dir: str = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Tuple[bool, str]:
    """Install all required packages into the virtual environment.

    Args:
        venv_dir: Path to the virtual environment. Defaults to VENV_DIR.
        progress_callback: Optional callback(percent, message) for progress.
        cancel_check: Optional callback that returns True if cancelled.

    Returns:
        A tuple of (success, message).
    """
    if venv_dir is None:
        venv_dir = VENV_DIR

    total_packages = len(REQUIRED_PACKAGES)
    cumulative_weight = 0.0

    for i, (pkg_name, pkg_version) in enumerate(REQUIRED_PACKAGES):
        if cancel_check and cancel_check():
            return False, "Installation cancelled"

        package_spec = pkg_name
        if pkg_version:
            package_spec = f"{pkg_name}{pkg_version}"

        weight = _PACKAGE_WEIGHTS.get(pkg_name, 1.0 / total_packages)
        base_percent = int(cumulative_weight * 100)

        if progress_callback:
            progress_callback(
                base_percent,
                f"Installing {pkg_name} ({i + 1}/{total_packages})...",
            )

        # Try installation with retry logic
        success = False
        last_error = ""

        for attempt in range(3):
            extra_args = []

            if attempt == 1 and _is_ssl_error(last_error):
                _log(f"Retrying {pkg_name} with trusted hosts (SSL error)")
                extra_args = [
                    "--trusted-host",
                    "pypi.org",
                    "--trusted-host",
                    "files.pythonhosted.org",
                ]
            elif attempt == 1 and _is_hash_error(last_error):
                _log(f"Retrying {pkg_name} with --no-cache-dir (hash error)")
                extra_args = ["--no-cache-dir"]
            elif attempt > 0 and _is_network_error(last_error):
                _log(f"Retrying {pkg_name} after network error (attempt {attempt + 1})")
                time.sleep(5)
            elif attempt > 0:
                # For other errors, no point retrying
                break

            ok, stdout, stderr = _run_pip_install(
                venv_dir, package_spec, extra_args=extra_args
            )

            if ok:
                success = True
                break

            last_error = stderr
            _log(
                f"pip install {pkg_name} failed (attempt {attempt + 1}): {stderr}",
                Qgis.Warning,
            )

        if not success:
            return False, f"Failed to install {pkg_name}:\n{last_error}"

        cumulative_weight += weight
        if progress_callback:
            progress_callback(
                int(cumulative_weight * 100),
                f"Installed {pkg_name}",
            )

    return True, "All packages installed"


def verify_venv(
    venv_dir: str = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Tuple[bool, str]:
    """Verify that all required packages can be imported in the venv.

    Args:
        venv_dir: Path to the virtual environment. Defaults to VENV_DIR.
        progress_callback: Optional callback(percent, message) for progress.

    Returns:
        A tuple of (success, message).
    """
    if venv_dir is None:
        venv_dir = VENV_DIR

    if progress_callback:
        progress_callback(0, "Verifying packages...")

    venv_python = get_venv_python_path(venv_dir)
    verify_code = "import ee; import geemap; print('ok')"

    try:
        result = subprocess.run(
            [venv_python, "-c", verify_code],
            capture_output=True,
            text=True,
            timeout=60,
            env=_get_clean_env(),
            **_get_subprocess_kwargs(),
        )

        if result.returncode == 0 and "ok" in result.stdout:
            if progress_callback:
                progress_callback(100, "Verification passed")
            _log("Package verification passed")
            return True, "All packages verified"

        error_msg = result.stderr.strip() or result.stdout.strip()
        _log(f"Package verification failed: {error_msg}", Qgis.Warning)
        return False, f"Package verification failed:\n{error_msg}"

    except subprocess.TimeoutExpired:
        _log("Package verification timed out", Qgis.Warning)
        return False, "Package verification timed out (60s)"
    except Exception as e:
        _log(f"Package verification error: {e}", Qgis.Warning)
        return False, f"Package verification error:\n{e}"


def create_venv_and_install(
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Tuple[bool, str]:
    """Create the virtual environment and install all dependencies.

    This is the main orchestrator function. Progress is reported as:
    - 0-10%: Create virtual environment
    - 10-90%: Install packages
    - 90-100%: Verify installation

    Args:
        progress_callback: Optional callback(percent, message) for progress.
        cancel_check: Optional callback that returns True if cancelled.

    Returns:
        A tuple of (success, message).
    """
    _log(f"Starting dependency installation to {VENV_DIR}")
    _log(f"Platform: {platform.system()} {platform.machine()}")
    _log(f"Python: {sys.version}")

    # Step 1: Create venv (0-10%)
    def venv_progress(percent, msg):
        if progress_callback:
            # Map 0-100 to 0-10
            progress_callback(int(percent * 0.10), msg)

    ok, msg = create_venv(progress_callback=venv_progress)
    if not ok:
        return False, msg

    if cancel_check and cancel_check():
        return False, "Installation cancelled"

    # Step 2: Install packages (10-90%)
    def install_progress(percent, msg):
        if progress_callback:
            # Map 0-100 to 10-90
            mapped = 10 + int(percent * 0.80)
            progress_callback(mapped, msg)

    ok, msg = install_dependencies(
        progress_callback=install_progress,
        cancel_check=cancel_check,
    )
    if not ok:
        return False, msg

    if cancel_check and cancel_check():
        return False, "Installation cancelled"

    # Step 3: Verify (90-100%)
    def verify_progress(percent, msg):
        if progress_callback:
            # Map 0-100 to 90-100
            mapped = 90 + int(percent * 0.10)
            progress_callback(mapped, msg)

    ok, msg = verify_venv(progress_callback=verify_progress)
    if not ok:
        return False, msg

    # Write deps hash to track this successful install
    _write_deps_hash()

    if progress_callback:
        progress_callback(100, "Dependencies installed successfully")

    _log("All dependencies installed and verified")
    return True, "Dependencies installed successfully"


def remove_venv(venv_dir: str = None) -> Tuple[bool, str]:
    """Remove the virtual environment directory.

    Args:
        venv_dir: Path to the virtual environment. Defaults to VENV_DIR.

    Returns:
        A tuple of (success, message).
    """
    if venv_dir is None:
        venv_dir = VENV_DIR

    if not os.path.exists(venv_dir):
        return True, "Virtual environment does not exist"

    try:
        shutil.rmtree(venv_dir)
        _log(f"Removed venv: {venv_dir}")
        return True, "Virtual environment removed"
    except Exception as e:
        _log(f"Failed to remove venv: {e}", Qgis.Warning)
        return False, f"Failed to remove virtual environment:\n{e}"
