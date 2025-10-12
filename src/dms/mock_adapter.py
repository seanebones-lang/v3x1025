"""
Mock DMS adapter for demo and testing purposes.
Generates realistic automotive dealership data.
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from src.dms.base import BaseDMSAdapter
from src.models import Vehicle


class MockDMSAdapter(BaseDMSAdapter):
    """Mock DMS adapter that generates realistic demo data."""
    
    def __init__(self, api_key: str = "mock", api_url: str = "mock://localhost", **kwargs):
        """Initialize mock adapter with demo data."""
        super().__init__(api_key, api_url, **kwargs)
        self._generate_mock_inventory()
    
    def _generate_mock_inventory(self):
        """Generate realistic mock inventory data."""
        makes_models = {
            "Toyota": ["Camry", "Corolla", "RAV4", "Highlander", "Tacoma", "4Runner"],
            "Honda": ["Accord", "Civic", "CR-V", "Pilot", "Ridgeline"],
            "Ford": ["F-150", "Mustang", "Explorer", "Escape", "Edge", "Bronco"],
            "Chevrolet": ["Silverado", "Equinox", "Malibu", "Tahoe", "Traverse"],
            "Tesla": ["Model 3", "Model Y", "Model S", "Model X"],
            "BMW": ["3 Series", "5 Series", "X3", "X5"],
            "Mercedes-Benz": ["C-Class", "E-Class", "GLE", "GLC"]
        }
        
        colors = ["Black", "White", "Silver", "Gray", "Blue", "Red", "Green"]
        transmissions = ["Automatic", "Manual", "CVT"]
        fuel_types = ["Gasoline", "Diesel", "Electric", "Hybrid", "Plug-in Hybrid"]
        statuses = ["available", "available", "available", "pending", "sold"]
        
        self.inventory = []
        
        for i in range(50):
            make = random.choice(list(makes_models.keys()))
            model = random.choice(makes_models[make])
            year = random.randint(2020, 2025)
            
            # Generate VIN (simplified)
            vin = f"{''.join(random.choices('ABCDEFGHJKLMNPRSTUVWXYZ1234567890', k=17))}"
            
            # Set fuel type based on make
            if make == "Tesla":
                fuel_type = "Electric"
            else:
                fuel_type = random.choice(fuel_types)
            
            vehicle = Vehicle(
                vin=vin,
                make=make,
                model=model,
                year=year,
                trim=random.choice(["Base", "Sport", "Limited", "Premium", "LE", "SE"]),
                mileage=random.randint(0, 50000),
                price=round(random.uniform(20000, 80000), 2),
                status=random.choice(statuses),
                color_exterior=random.choice(colors),
                color_interior=random.choice(["Black", "Beige", "Gray"]),
                engine=f"{random.choice(['2.0L', '2.5L', '3.0L', '3.5L', '5.0L'])} {random.choice(['I4', 'V6', 'V8'])}",
                transmission=random.choice(transmissions),
                fuel_type=fuel_type,
                features=[
                    random.choice(["Backup Camera", "Bluetooth", "Navigation", "Sunroof", 
                                 "Leather Seats", "Heated Seats", "Apple CarPlay", "Android Auto"])
                    for _ in range(random.randint(2, 6))
                ],
                images=[],
                location="Main Dealership",
                stock_number=f"STK{i+1001}",
                created_at=datetime.now() - timedelta(days=random.randint(1, 90)),
                updated_at=datetime.now()
            )
            
            self.inventory.append(vehicle)
    
    async def get_inventory(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Vehicle]:
        """Get inventory with optional filtering."""
        result = self.inventory.copy()
        
        if filters:
            if "make" in filters:
                result = [v for v in result if v.make.lower() == filters["make"].lower()]
            if "model" in filters:
                result = [v for v in result if v.model.lower() == filters["model"].lower()]
            if "year" in filters:
                result = [v for v in result if v.year == filters["year"]]
            if "min_price" in filters:
                result = [v for v in result if v.price and v.price >= filters["min_price"]]
            if "max_price" in filters:
                result = [v for v in result if v.price and v.price <= filters["max_price"]]
            if "status" in filters:
                result = [v for v in result if v.status == filters["status"]]
            if "fuel_type" in filters:
                result = [v for v in result if v.fuel_type == filters["fuel_type"]]
        
        return result[offset:offset + limit]
    
    async def get_vehicle_details(self, vin: str) -> Optional[Vehicle]:
        """Get details for a specific vehicle by VIN."""
        for vehicle in self.inventory:
            if vehicle.vin == vin:
                return vehicle
        return None
    
    async def sync_pricing(self) -> Dict[str, Any]:
        """Mock pricing synchronization."""
        # Randomly adjust prices slightly
        updated = 0
        for vehicle in self.inventory:
            if random.random() < 0.3:  # 30% chance of price update
                if vehicle.price:
                    adjustment = random.uniform(-0.05, 0.05)  # ±5%
                    vehicle.price = round(vehicle.price * (1 + adjustment), 2)
                    vehicle.updated_at = datetime.now()
                    updated += 1
        
        return {
            "status": "success",
            "updated_count": updated,
            "total_count": len(self.inventory),
            "timestamp": datetime.now().isoformat()
        }
    
    async def get_service_history(self, vin: str) -> List[Dict[str, Any]]:
        """Get mock service history for a vehicle."""
        vehicle = await self.get_vehicle_details(vin)
        if not vehicle:
            return []
        
        service_types = [
            "Oil Change",
            "Tire Rotation",
            "Brake Inspection",
            "Battery Replacement",
            "Transmission Service",
            "Air Filter Replacement",
            "Coolant Flush"
        ]
        
        num_services = random.randint(1, 5)
        history = []
        
        for i in range(num_services):
            history.append({
                "service_date": (datetime.now() - timedelta(days=random.randint(30, 365))).isoformat(),
                "service_type": random.choice(service_types),
                "mileage_at_service": random.randint(5000, vehicle.mileage or 50000),
                "cost": round(random.uniform(50, 500), 2),
                "notes": "Service completed successfully"
            })
        
        return sorted(history, key=lambda x: x["service_date"], reverse=True)
    
    async def check_availability(self, vin: str) -> bool:
        """Check if a vehicle is available."""
        vehicle = await self.get_vehicle_details(vin)
        if not vehicle:
            return False
        return vehicle.status == "available"
    
    async def search_vehicles(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Vehicle]:
        """Simple text search across vehicle attributes."""
        query_lower = query.lower()
        result = []
        
        for vehicle in self.inventory:
            # Search in make, model, features, etc.
            searchable_text = f"{vehicle.make} {vehicle.model} {vehicle.year} {vehicle.color_exterior} {' '.join(vehicle.features)}"
            if query_lower in searchable_text.lower():
                result.append(vehicle)
        
        # Apply additional filters if provided
        if filters:
            temp_result = result
            result = []
            for vehicle in temp_result:
                match = True
                for key, value in filters.items():
                    if hasattr(vehicle, key) and getattr(vehicle, key) != value:
                        match = False
                        break
                if match:
                    result.append(vehicle)
        
        return result

