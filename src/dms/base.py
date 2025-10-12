"""
Abstract base class for DMS adapters.
Defines the interface that all DMS adapters must implement.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime

from src.models import Vehicle


class BaseDMSAdapter(ABC):
    """Abstract base class for DMS adapters."""
    
    def __init__(self, api_key: str, api_url: str, **kwargs):
        """
        Initialize the DMS adapter.
        
        Args:
            api_key: API key for authentication
            api_url: Base URL for the DMS API
            **kwargs: Additional configuration parameters
        """
        self.api_key = api_key
        self.api_url = api_url
        self.config = kwargs
    
    @abstractmethod
    async def get_inventory(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Vehicle]:
        """
        Retrieve inventory from the DMS.
        
        Args:
            filters: Optional filters (e.g., make, model, year, price_range)
            limit: Maximum number of vehicles to return
            offset: Pagination offset
            
        Returns:
            List of Vehicle objects
        """
        pass
    
    @abstractmethod
    async def get_vehicle_details(self, vin: str) -> Optional[Vehicle]:
        """
        Get detailed information for a specific vehicle.
        
        Args:
            vin: Vehicle Identification Number
            
        Returns:
            Vehicle object or None if not found
        """
        pass
    
    @abstractmethod
    async def sync_pricing(self) -> Dict[str, Any]:
        """
        Synchronize pricing data from the DMS.
        
        Returns:
            Dictionary with sync statistics (updated_count, error_count, etc.)
        """
        pass
    
    @abstractmethod
    async def get_service_history(self, vin: str) -> List[Dict[str, Any]]:
        """
        Get service history for a vehicle.
        
        Args:
            vin: Vehicle Identification Number
            
        Returns:
            List of service records
        """
        pass
    
    @abstractmethod
    async def check_availability(self, vin: str) -> bool:
        """
        Check if a vehicle is available for sale.
        
        Args:
            vin: Vehicle Identification Number
            
        Returns:
            True if available, False otherwise
        """
        pass
    
    @abstractmethod
    async def search_vehicles(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Vehicle]:
        """
        Search vehicles using natural language query.
        
        Args:
            query: Natural language search query
            filters: Optional additional filters
            
        Returns:
            List of matching Vehicle objects
        """
        pass
    
    async def health_check(self) -> bool:
        """
        Check if the DMS connection is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            # Default implementation: try to get inventory with limit 1
            await self.get_inventory(limit=1)
            return True
        except Exception:
            return False
    
    def _build_headers(self) -> Dict[str, str]:
        """
        Build common request headers.
        
        Returns:
            Dictionary of HTTP headers
        """
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Dealership-RAG/1.0"
        }

