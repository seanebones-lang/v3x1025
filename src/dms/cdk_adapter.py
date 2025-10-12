"""
CDK Global DMS adapter.
Integrates with CDK Global's automotive dealership management system.
"""

import aiohttp
from typing import Dict, List, Optional, Any
from tenacity import retry, stop_after_attempt, wait_exponential

from src.dms.base import BaseDMSAdapter
from src.models import Vehicle


class CDKAdapter(BaseDMSAdapter):
    """CDK Global DMS adapter with retry logic and error handling."""
    
    def __init__(self, api_key: str, api_url: str, **kwargs):
        """
        Initialize CDK adapter.
        
        Args:
            api_key: CDK API key
            api_url: CDK API base URL
            **kwargs: Additional configuration (dealer_id, timeout, etc.)
        """
        super().__init__(api_key, api_url, **kwargs)
        self.dealer_id = kwargs.get("dealer_id", "")
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
        Make HTTP request to CDK API with retry logic.
        
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
        Retrieve inventory from CDK Global.
        
        Args:
            filters: Optional filters
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            List of Vehicle objects
        """
        params = {
            "dealerId": self.dealer_id,
            "limit": limit,
            "offset": offset
        }
        
        if filters:
            params.update(filters)
        
        try:
            response = await self._make_request("GET", "inventory", params=params)
            vehicles = []
            
            for item in response.get("vehicles", []):
                vehicle = self._map_cdk_vehicle(item)
                vehicles.append(vehicle)
            
            return vehicles
        except Exception as e:
            raise Exception(f"Failed to fetch CDK inventory: {str(e)}")
    
    async def get_vehicle_details(self, vin: str) -> Optional[Vehicle]:
        """Get vehicle details by VIN from CDK."""
        try:
            response = await self._make_request(
                "GET",
                f"inventory/vehicle/{vin}",
                params={"dealerId": self.dealer_id}
            )
            return self._map_cdk_vehicle(response)
        except aiohttp.ClientResponseError as e:
            if e.status == 404:
                return None
            raise
    
    async def sync_pricing(self) -> Dict[str, Any]:
        """Sync pricing data from CDK."""
        try:
            response = await self._make_request(
                "POST",
                "pricing/sync",
                json_data={"dealerId": self.dealer_id}
            )
            return {
                "status": "success",
                "updated_count": response.get("updatedCount", 0),
                "error_count": response.get("errorCount", 0),
                "timestamp": response.get("timestamp")
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "updated_count": 0,
                "error_count": 1
            }
    
    async def get_service_history(self, vin: str) -> List[Dict[str, Any]]:
        """Get service history from CDK."""
        try:
            response = await self._make_request(
                "GET",
                f"service/history/{vin}",
                params={"dealerId": self.dealer_id}
            )
            return response.get("serviceRecords", [])
        except Exception:
            return []
    
    async def check_availability(self, vin: str) -> bool:
        """Check vehicle availability in CDK."""
        vehicle = await self.get_vehicle_details(vin)
        if not vehicle:
            return False
        return vehicle.status == "available"
    
    async def search_vehicles(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Vehicle]:
        """Search vehicles in CDK using text query."""
        params = {
            "dealerId": self.dealer_id,
            "q": query
        }
        
        if filters:
            params.update(filters)
        
        try:
            response = await self._make_request("GET", "inventory/search", params=params)
            vehicles = []
            
            for item in response.get("results", []):
                vehicle = self._map_cdk_vehicle(item)
                vehicles.append(vehicle)
            
            return vehicles
        except Exception:
            return []
    
    def _map_cdk_vehicle(self, data: Dict) -> Vehicle:
        """
        Map CDK API response to Vehicle model.
        
        Args:
            data: CDK vehicle data
            
        Returns:
            Vehicle object
        """
        return Vehicle(
            vin=data.get("vin", ""),
            make=data.get("make", ""),
            model=data.get("model", ""),
            year=int(data.get("year", 0)),
            trim=data.get("trim"),
            mileage=data.get("mileage"),
            price=data.get("price"),
            status=self._map_status(data.get("status", "")),
            color_exterior=data.get("exteriorColor"),
            color_interior=data.get("interiorColor"),
            engine=data.get("engine"),
            transmission=data.get("transmission"),
            fuel_type=data.get("fuelType"),
            features=data.get("features", []),
            images=data.get("images", []),
            location=data.get("location"),
            stock_number=data.get("stockNumber"),
            created_at=data.get("createdAt"),
            updated_at=data.get("updatedAt")
        )
    
    @staticmethod
    def _map_status(cdk_status: str) -> str:
        """Map CDK status to internal status."""
        status_map = {
            "IN_STOCK": "available",
            "AVAILABLE": "available",
            "SOLD": "sold",
            "PENDING_SALE": "pending",
            "IN_SERVICE": "service"
        }
        return status_map.get(cdk_status.upper(), "available")

