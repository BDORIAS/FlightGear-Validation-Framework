# FlightGear Test Framework

FlightGear Test Framework is a local automation toolkit for running FlightGear
test profiles, collecting telemetry, and inspecting the resulting CSV data with
an interactive telemetry viewer.

The current built-in scenario is a C172P cruise engine-failure test. The
framework is structured so additional profiles can be added under
`src/flightgear_framework/testing`.

## Features

- Visual terminal console for selecting and running test profiles.
- FlightGear process management that keeps the console alive if the simulator exits.
- Telnet property protocol for reading and writing FlightGear state.
- CSV telemetry capture and focused viewer windows around test events.
- Optional C++ math helpers with a pure-Python fallback.
- Portable configuration through YAML and environment variables.

## Project Layout

```text
config/                         Default framework configuration.
cpp_modules/                    Optional C++ extension sources.
data/results/                   Runtime outputs; ignored except .gitkeep.
src/flightgear_framework/       Python package.
tests/unit/                     Unit tests for console, viewer, native bridge, and runner logic.
```

## Setup

Create a virtual environment and install the direct dependencies:

```powershell
python -m venv venv_flightgear
.\venv_flightgear\Scripts\python.exe -m pip install -r requirements.txt
```

On Linux, macOS, or Git Bash:

```bash
python -m venv venv_flightgear
./venv_flightgear/bin/python -m pip install -r requirements.txt
```

FlightGear itself must be installed separately. If `fgfs` is not on `PATH`, set
`FGFS_EXECUTABLE` to the executable path.

## Configuration

Default settings live in `config/framework_config.yaml`. User-specific paths
should not be committed. Prefer environment variables for local overrides:

```text
FGFS_EXECUTABLE       FlightGear executable, defaults to fgfs.
FG_ROOT               Optional FlightGear data directory.
FG_AIRCRAFT           Aircraft id, defaults to c172p.
FG_AIRPORT            Startup airport, defaults to BIKF.
FG_RUNWAY             Startup runway, defaults to 29.
FG_HOST               Telnet host, defaults to localhost.
FG_TELNET_PORT        Telnet port, defaults to 5401.
FG_RESPONSE_TIMEOUT   Per-command telnet timeout.
FG_DISABLE_TERRASYNC  true/false.
FG_RESULTS_DIR        Optional output directory for generated results.
```

## Running The Console

Windows:

```powershell
.\run_console.ps1
```

Cross-platform Python entrypoint:

```bash
PYTHONPATH=src ./venv_flightgear/bin/python -m flightgear_framework.console_app
```

Useful console commands:

```bash
python -m flightgear_framework.console_app --list
python -m flightgear_framework.console_app --status
python -m flightgear_framework.console_app --dry-run cruise_engine_failure
```

## Running Tests

Windows:

```powershell
.\venv_flightgear\Scripts\python.exe -m pytest tests\unit -q
```

Linux, macOS, or Git Bash:

```bash
./run_tests.sh tests/unit -q
```

## Viewer

After a profile has generated its CSV, open the viewer:

```bash
python -m flightgear_framework.viewer --profile cruise_engine_failure --open-browser
```

The viewer focuses on the configured event window. For the engine-failure
profile, it shows 10 seconds before failure plus 30 seconds of failure/glide
data.

Use the `PDF Report` button in the viewer to generate a print-ready flight test report.
The report includes test metadata, aircraft/runway summary, validation metrics,
control-surface statistics, key flight signals, and the configured charts. The
browser print dialog can save it as a PDF.

## Optional C++ Backend

The package imports `flightgear_framework.native` safely even when the C++
extension has not been built. In that case it uses the Python fallback.

When the console starts on Windows, it attempts to build and load the C++
backend automatically. The attempt is safe: if Visual C++ Build Tools or any
other build dependency is missing, the console keeps running with the Python
fallback. Disable the automatic attempt with:

```powershell
$env:FG_NATIVE_AUTO_BUILD = "0"
```

To build the native extension from the project root:

```powershell
.\venv_flightgear\Scripts\python.exe .\cpp_modules\setup.py build_ext --inplace
```

Compiled native binaries are ignored by Git because they are platform-specific.
