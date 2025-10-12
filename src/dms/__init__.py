"""
DMS (Dealership Management System) integration layer.
Provides adapters for various DMS platforms using the adapter pattern.
"""

from src.dms.base import BaseDMSAdapter
from src.dms.mock_adapter import MockDMSAdapter
from src.dms.cdk_adapter import CDKAdapter
from src.dms.reynolds_adapter import ReynoldsAdapter

__all__ = [
    "BaseDMSAdapter",
    "MockDMSAdapter",
    "CDKAdapter",
    "ReynoldsAdapter",
]

