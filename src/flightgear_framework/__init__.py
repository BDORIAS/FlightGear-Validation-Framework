"""Public package API for the FlightGear Test Framework."""

__version__ = "1.0.0"
__author__ = "FlightGear Test Framework contributors"

from .core.simulator import FlightGearSimulator
from .communication.protocol import FlightGearProtocol
from .testing.test_runner import TestRunner

__all__ = [
    'FlightGearSimulator',
    'FlightGearProtocol',
    'TestRunner',
]
