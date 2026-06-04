# FlightGear native C++ modules

This directory contains optional C++ helpers exposed to Python with `pybind11`.
The Python framework always has a pure-Python fallback, so failing to compile
this module must not break FlightGear tests.

Build from the project root:

```powershell
.\venv_flightgear\Scripts\python.exe .\cpp_modules\setup.py build_ext --inplace
```

The compiled extension is imported as:

```python
flightgear_framework.native._flightgear_native
```

Current native helpers cover deterministic, frequently repeated math:

- value clamping
- heading error/delta wrapping
- runway centerline tracking metrics
