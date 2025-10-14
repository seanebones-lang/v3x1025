"""
Abstract base class for Dealer Management System (DMS) adapters.
Defines a standard interface for interacting with different DMS providers.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from src.models import Vehicle


class BaseDMSAdapter(ABC):
    """Abstract base class for DMS adapters."""

    @abstractmethod
    async def get_inventory(
        self,
        filters: Optional[dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Vehicle]:
        """
        Get vehicle inventory from the DMS.

        Args:
            filters: Dictionary of filters to apply (e.g., {"make": "Toyota"})
            limit: Maximum number of vehicles to return
            offset: Number of vehicles to skip for pagination

        Returns:
            List of Vehicle objects
        """
        pass

    @abstractmethod
    async def get_vehicle_details(self, vin: str) -> Optional[Vehicle]:
        """
        Get details for a specific vehicle by VIN.

        Args:
            vin: Vehicle Identification Number

        Returns:
            Vehicle object or None if not found
        """
        pass

    @abstractmethod
    async def get_service_history(self, vin: str) -> list[dict[str, Any]]:
        """
        Get service history for a specific vehicle by VIN.

        Args:
            vin: Vehicle Identification Number

        Returns:
            List of service records
        """
        pass

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """
        Perform a health check on the DMS API.

        Returns:
            Dictionary with health status information
        """
        pass