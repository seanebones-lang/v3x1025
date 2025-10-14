"""
Mock DMS adapter for testing and development.
Provides simulated responses without requiring actual DMS connections.
"""

import asyncio
import logging
import random
from typing import Any, Optional

from src.dms.base import BaseDMSAdapter
from src.models import Vehicle

logger = logging.getLogger(__name__)


class MockDMSAdapter(BaseDMSAdapter):
    """Mock DMS adapter for testing and development environments."""

    def __init__(self):
        """Initialize the mock DMS adapter."""
        self.name = "MockDMS"
        
        # Mock inventory data
        self.mock_vehicles = [
            Vehicle(
                vin="1FTFW1ET5DFC00001",
                make="Ford",
                model="F-150",
                year=2023,
                price=45500.0,
                mileage=12,
                status="available",
                features=["4WD", "Crew Cab", "V6 Engine", "Bluetooth"],
                image_url="https://example.com/ford-f150.jpg"
            ),
            Vehicle(
                vin="1N4AL3AP8DC000002",
                make="Toyota",
                model="Camry",
                year=2022,
                price=28900.0,
                mileage=15400,
                status="available",
                features=["Hybrid", "Lane Assist", "Backup Camera", "Apple CarPlay"],
                image_url="https://example.com/toyota-camry.jpg"
            ),
            Vehicle(
                vin="5YJ3E1EA6KF000003",
                make="Tesla",
                model="Model 3",
                year=2023,
                price=42000.0,
                mileage=8500,
                status="available",
                features=["Electric", "Autopilot", "Premium Audio", "Glass Roof"],
                image_url="https://example.com/tesla-model3.jpg"
            ),
            Vehicle(
                vin="1HGBH41JXMN000004",
                make="Honda",
                model="Accord",
                year=2021,
                price=31200.0,
                mileage=22800,
                status="sold",
                features=["Honda Sensing", "Moonroof", "Heated Seats", "Navigation"],
                image_url="https://example.com/honda-accord.jpg"
            ),
            Vehicle(
                vin="WBA8E9G5XGNT00005",
                make="BMW",
                model="X3",
                year=2023,
                price=54900.0,
                mileage=3200,
                status="available",
                features=["xDrive", "Premium Package", "Heads-Up Display", "Wireless Charging"],
                image_url="https://example.com/bmw-x3.jpg"
            ),
        ]

    async def get_inventory(
        self,
        filters: Optional[dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Vehicle]:
        """
        Get mock vehicle inventory.

        Args:
            filters: Dictionary of filters to apply
            limit: Maximum number of vehicles to return
            offset: Number of vehicles to skip

        Returns:
            List of Vehicle objects
        """
        # Simulate API delay
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        logger.info(f"Mock DMS: Getting inventory with filters={filters}, limit={limit}, offset={offset}")
        
        vehicles = self.mock_vehicles.copy()
        
        # Apply filters if provided
        if filters:
            filtered_vehicles = []
            for vehicle in vehicles:
                match = True
                
                # Check make filter
                if "make" in filters and vehicle.make.lower() != filters["make"].lower():
                    match = False
                
                # Check year filter
                if "year" in filters and vehicle.year != filters["year"]:
                    match = False
                    
                # Check max price filter
                if "max_price" in filters and vehicle.price > filters["max_price"]:
                    match = False
                
                # Check min price filter
                if "min_price" in filters and vehicle.price < filters["min_price"]:
                    match = False
                
                # Check status filter
                if "status" in filters and vehicle.status != filters["status"]:
                    match = False
                
                if match:
                    filtered_vehicles.append(vehicle)
            
            vehicles = filtered_vehicles
        
        # Apply pagination
        start_idx = min(offset, len(vehicles))
        end_idx = min(start_idx + limit, len(vehicles))
        
        paginated_vehicles = vehicles[start_idx:end_idx]
        
        logger.info(f"Mock DMS: Returning {len(paginated_vehicles)} vehicles")
        return paginated_vehicles

    async def get_vehicle_details(self, vin: str) -> Optional[Vehicle]:
        """
        Get details for a specific vehicle by VIN.

        Args:
            vin: Vehicle Identification Number

        Returns:
            Vehicle object or None if not found
        """
        # Simulate API delay
        await asyncio.sleep(random.uniform(0.05, 0.15))
        
        logger.info(f"Mock DMS: Getting vehicle details for VIN={vin}")
        
        for vehicle in self.mock_vehicles:
            if vehicle.vin == vin:
                return vehicle
        
        logger.warning(f"Mock DMS: Vehicle not found for VIN={vin}")
        return None

    async def get_service_history(self, vin: str) -> list[dict[str, Any]]:
        """
        Get mock service history for a vehicle.

        Args:
            vin: Vehicle Identification Number

        Returns:
            List of service records
        """
        # Simulate API delay
        await asyncio.sleep(random.uniform(0.1, 0.2))
        
        logger.info(f"Mock DMS: Getting service history for VIN={vin}")
        
        # Check if vehicle exists
        vehicle = await self.get_vehicle_details(vin)
        if not vehicle:
            return []
        
        # Generate mock service history based on mileage
        service_records = []
        
        # Basic service records based on mileage
        if vehicle.mileage > 5000:
            service_records.append({
                "date": "2023-06-15",
                "mileage": 5200,
                "service_type": "Oil Change",
                "description": "Synthetic oil change, filter replacement",
                "cost": 85.50,
                "technician": "Mike Johnson",
                "status": "completed"
            })
        
        if vehicle.mileage > 15000:
            service_records.append({
                "date": "2023-03-10", 
                "mileage": 15800,
                "service_type": "Scheduled Maintenance",
                "description": "15k mile service, tire rotation, brake inspection",
                "cost": 245.00,
                "technician": "Sarah Williams",
                "status": "completed"
            })
        
        if vehicle.mileage > 25000:
            service_records.append({
                "date": "2022-12-05",
                "mileage": 25300,
                "service_type": "Brake Service", 
                "description": "Front brake pad replacement",
                "cost": 320.75,
                "technician": "David Chen",
                "status": "completed"
            })
        
        logger.info(f"Mock DMS: Returning {len(service_records)} service records")
        return service_records

    async def health_check(self) -> dict[str, Any]:
        """
        Perform health check on mock DMS.

        Returns:
            Dictionary with health status
        """
        # Simulate quick health check
        await asyncio.sleep(0.05)
        
        return {
            "status": "healthy",
            "adapter": "MockDMS",
            "vehicles_available": len(self.mock_vehicles),
            "response_time_ms": 50,
            "last_sync": "2023-10-12T10:30:00Z",
            "api_version": "mock-1.0.0"
        }