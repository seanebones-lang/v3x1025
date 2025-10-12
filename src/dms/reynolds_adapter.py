"""
Reynolds & Reynolds DMS adapter.
Integrates with Reynolds & Reynolds dealership management system.
"""

import aiohttp
from typing import Dict, List, Optional, Any
from tenacity import retry, stop_after_attempt, wait_exponential

from src.dms.base import BaseDMSAdapter
from src.models import Vehicle


class ReynoldsAdapter(BaseDMSAdapter):
    """Reynolds & Reynolds DMS adapter with retry logic and error handling."""
    
    def __init__(self, api_key: str, api_url: str, **kwargs):
        """
        Initialize Reynolds adapter.
        
        Args:
            api_key: Reynolds API key
            api_url: Reynolds API base URL
            **kwargs: Additional configuration (dealer_code, timeout, etc.)
        """
        super().__init__(api_key, api_url, **kwargs)
        self.dealer_code = kwargs.get("dealer_code", "")
        self.timeout = kwargs.get("timeout", 30)
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None
    ) -> Dict:
        """
        Make HTTP request to Reynolds API with retry logic.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            json_data: JSON body
            
        Returns:
            Response JSON
        """
        url = f"{self.api_url}/{endpoint}"
        headers = self._build_headers()
        headers["X-Dealer-Code"] = self.dealer_code
        
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_data,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                response.raise_for_status()
                return await response.json()
    
    async def get_inventory(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Vehicle]:
        """
        Retrieve inventory from Reynolds & Reynolds.
        
        Args:
            filters: Optional filters
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            List of Vehicle objects
        """
        params = {
            "limit": limit,
            "offset": offset
        }
        
        if filters:
            # Map filters to Reynolds API format
            if "make" in filters:
                params["manufacturer"] = filters["make"]
            if "model" in filters:
                params["model"] = filters["model"]
            if "year" in filters:
                params["modelYear"] = filters["year"]
        
        try:
            response = await self._make_request("GET", "vehicles", params=params)
            vehicles = []
            
            for item in response.get("data", []):
                vehicle = self._map_reynolds_vehicle(item)
                vehicles.append(vehicle)
            
            return vehicles
        except Exception as e:
            raise Exception(f"Failed to fetch Reynolds inventory: {str(e)}")
    
    async def get_vehicle_details(self, vin: str) -> Optional[Vehicle]:
        """Get vehicle details by VIN from Reynolds."""
        try:
            response = await self._make_request("GET", f"vehicles/{vin}")
            return self._map_reynolds_vehicle(response.get("data", {}))
        except aiohttp.ClientResponseError as e:
            if e.status == 404:
                return None
            raise
    
    async def sync_pricing(self) -> Dict[str, Any]:
        """Sync pricing data from Reynolds."""
        try:
            response = await self._make_request("POST", "pricing/refresh")
            return {
                "status": "success",
                "updated_count": response.get("updated", 0),
                "error_count": response.get("errors", 0),
                "timestamp": response.get("processedAt")
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "updated_count": 0,
                "error_count": 1
            }
    
    async def get_service_history(self, vin: str) -> List[Dict[str, Any]]:
        """Get service history from Reynolds."""
        try:
            response = await self._make_request("GET", f"service/{vin}/history")
            return response.get("records", [])
        except Exception:
            return []
    
    async def check_availability(self, vin: str) -> bool:
        """Check vehicle availability in Reynolds."""
        vehicle = await self.get_vehicle_details(vin)
        if not vehicle:
            return False
        return vehicle.status == "available"
    
    async def search_vehicles(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Vehicle]:
        """Search vehicles in Reynolds using text query."""
        params = {"search": query}
        
        if filters:
            params.update(filters)
        
        try:
            response = await self._make_request("GET", "vehicles/search", params=params)
            vehicles = []
            
            for item in response.get("data", []):
                vehicle = self._map_reynolds_vehicle(item)
                vehicles.append(vehicle)
            
            return vehicles
        except Exception:
            return []
    
    def _map_reynolds_vehicle(self, data: Dict) -> Vehicle:
        """
        Map Reynolds API response to Vehicle model.
        
        Args:
            data: Reynolds vehicle data
            
        Returns:
            Vehicle object
        """
        return Vehicle(
            vin=data.get("vehicleIdentificationNumber", ""),
            make=data.get("manufacturer", ""),
            model=data.get("model", ""),
            year=int(data.get("modelYear", 0)),
            trim=data.get("trimLevel"),
            mileage=data.get("odometer"),
            price=data.get("retailPrice"),
            status=self._map_status(data.get("inventoryStatus", "")),
            color_exterior=data.get("exteriorColorDescription"),
            color_interior=data.get("interiorColorDescription"),
            engine=data.get("engineDescription"),
            transmission=data.get("transmissionDescription"),
            fuel_type=data.get("fuelType"),
            features=data.get("optionDescriptions", []),
            images=data.get("imageUrls", []),
            location=data.get("dealershipLocation"),
            stock_number=data.get("stockNumber"),
            created_at=data.get("dateCreated"),
            updated_at=data.get("dateModified")
        )
    
    @staticmethod
    def _map_status(reynolds_status: str) -> str:
        """Map Reynolds status to internal status."""
        status_map = {
            "AVAILABLE": "available",
            "IN_STOCK": "available",
            "SOLD": "sold",
            "PENDING": "pending",
            "SERVICE": "service",
            "WORKSHOP": "service"
        }
        return status_map.get(reynolds_status.upper(), "available")

