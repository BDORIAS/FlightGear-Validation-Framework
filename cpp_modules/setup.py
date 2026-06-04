"""Build script for the optional FlightGear native helper extension."""

from pathlib import Path

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext

try:
    import pybind11
except ImportError as exc:
    raise SystemExit(
        "pybind11 is required to build the native extension. "
        "Install it in venv_flightgear first."
    ) from exc


MODULE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MODULE_DIR.parent


class BuildExt(build_ext):
    compile_args = {
        "msvc": ["/std:c++17", "/O2"],
        "unix": ["-std=c++17", "-O3"],
    }

    def build_extensions(self):
        compiler_type = self.compiler.compiler_type
        for extension in self.extensions:
            extension.extra_compile_args = self.compile_args.get(
                compiler_type,
                ["-std=c++17"],
            )
        super().build_extensions()


extension = Extension(
    "flightgear_framework.native._flightgear_native",
    sources=[
        str(MODULE_DIR / "src" / "flightgear_native.cpp"),
        str(MODULE_DIR / "src" / "bindings.cpp"),
    ],
    include_dirs=[
        str(MODULE_DIR / "include"),
        pybind11.get_include(),
    ],
    language="c++",
)


setup(
    name="flightgear-framework-native",
    version="0.1.0",
    description="Optional native helpers for FlightGear Test Framework",
    ext_modules=[extension],
    cmdclass={"build_ext": BuildExt},
    package_dir={"": str(PROJECT_ROOT / "src")},
)
