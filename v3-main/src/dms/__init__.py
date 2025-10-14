"""
DMS (Dealer Management System) adapters package.
Provides standardized interface for integrating with various automotive DMS providers.
"""

from .base import BaseDMSAdapter
from .cdk_adapter import CDKAdapter
from .mock_adapter import MockDMSAdapter
from .reynolds_adapter import ReynoldsAdapter

__all__ = [
    "BaseDMSAdapter",
    "CDKAdapter", 
    "MockDMSAdapter",
    "ReynoldsAdapter",
]