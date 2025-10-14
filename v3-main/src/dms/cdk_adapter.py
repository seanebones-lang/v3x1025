"""
Production CDK Global DMS adapter using Fortellis OAuth 2.0.
Implements secure authentication, rate limiting, and comprehensive error handling.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp
import jwt
from aiohttp import ClientSession, ClientTimeout

from src.config import get_config
from src.models import Vehicle
from .base import BaseDMSAdapter

logger = logging.getLogger(__name__)


class CDKAuthenticationError(Exception):
    """CDK authentication-specific errors."""
    pass


class CDKRateLimitError(Exception):
    """CDK rate limiting errors."""
    pass


class CDKAdapter(BaseDMSAdapter):
    """
    Production CDK Global adapter using Fortellis platform.
    
    Implements OAuth 2.0, rate limiting, token refresh, and comprehensive error handling.
    """

    def __init__(self):
        self.config = get_config()
        self.base_url = "https://api.fortellis.io"
        self.auth_url = "https://identity.fortellis.io/oauth2/aus1p1ob3f9VuIHDl2p7/v1/token"
        
        # OAuth 2.0 credentials
        self.client_id = self.config.cdk_api_key  # Client ID from environment
        self.client_secret = self.config.cdk_client_secret  # Client secret from environment
        self.dealer_id = self.config.cdk_dealer_id
        
        # Token management
        self.access_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        self.refresh_token: Optional[str] = None
        
        # Rate limiting (CDK allows 1000 requests per hour)
        self.rate_limit = 1000
        self.rate_window = 3600  # 1 hour
        self.request_timestamps: List[float] = []
        
        # HTTP session
        self.session: Optional[ClientSession] = None
        
        # Performance tracking
        self.total_requests = 0
        self.failed_requests = 0
        self.auth_failures = 0
        self.rate_limit_hits = 0
        
    async def initialize(self):
        """Initialize the CDK adapter with authentication."""
        if not self.client_id or not self.client_secret:
            raise CDKAuthenticationError(
                "CDK credentials not configured - check CDK_API_KEY and CDK_CLIENT_SECRET environment variables"
            )
        
        # Create HTTP session with proper configuration
        timeout = ClientTimeout(total=30, connect=10)
        self.session = ClientSession(
            timeout=timeout,
            headers={
                "User-Agent": "Blue1-RAG-System/1.0",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
        )
        
        # Authenticate
        await self.authenticate()
        logger.info("CDK adapter initialized successfully")

    async def authenticate(self) -> None:
        """
        Perform OAuth 2.0 client credentials flow authentication.
        
        Raises:
            CDKAuthenticationError: If authentication fails
        """
        try:
            auth_payload = {
                "grant_type": "client_credentials",
                "scope": "dealership:read vehicle:read service:read"
            }
            
            # Prepare basic auth header
            import base64
            credentials = f"{self.client_id}:{self.client_secret}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            
            auth_headers = {
                "Authorization": f"Basic {encoded_credentials}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            async with self.session.post(
                self.auth_url,
                data=auth_payload,
                headers=auth_headers
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    self.auth_failures += 1
                    raise CDKAuthenticationError(
                        f"CDK authentication failed with status {response.status}: {error_text}"
                    )
                
                auth_data = await response.json()
                
                # Extract tokens
                self.access_token = auth_data.get("access_token")
                expires_in = auth_data.get("expires_in", 3600)
                self.refresh_token = auth_data.get("refresh_token")
                
                if not self.access_token:
                    raise CDKAuthenticationError("No access token received from CDK")
                
                # Calculate expiration time with 5-minute buffer
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)
                
                logger.info(f"CDK authentication successful, token expires at {self.token_expires_at}")
                
        except Exception as e:
            if isinstance(e, CDKAuthenticationError):
                raise
            raise CDKAuthenticationError(f"CDK authentication failed: {str(e)}")

    async def ensure_authenticated(self) -> None:
        """Ensure we have a valid access token, refreshing if necessary."""
        if not self.access_token or not self.token_expires_at:
            await self.authenticate()
            return
        
        # Check if token is about to expire
        if datetime.now() >= self.token_expires_at:
            logger.info("CDK token expired, refreshing...")
            await self.authenticate()

    async def check_rate_limit(self) -> None:
        """
        Check and enforce rate limiting.
        
        Raises:
            CDKRateLimitError: If rate limit would be exceeded
        """
        now = time.time()
        
        # Remove timestamps outside the current window
        self.request_timestamps = [
            ts for ts in self.request_timestamps 
            if now - ts < self.rate_window
        ]
        
        # Check if we're at the limit
        if len(self.request_timestamps) >= self.rate_limit:
            self.rate_limit_hits += 1
            oldest_request = min(self.request_timestamps)
            wait_time = self.rate_window - (now - oldest_request)
            
            raise CDKRateLimitError(
                f"CDK rate limit exceeded. Wait {wait_time:.0f} seconds before next request."
            )
        
        # Record this request
        self.request_timestamps.append(now)

    async def make_authenticated_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Make authenticated request to CDK API with comprehensive error handling.
        
        Args:
            method: HTTP method
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON payload
            max_retries: Maximum retry attempts
            
        Returns:
            JSON response data
            
        Raises:
            CDKAuthenticationError: If authentication fails
            CDKRateLimitError: If rate limited
        """
        if not self.session:
            raise CDKAuthenticationError("CDK adapter not initialized")
        
        # Check rate limiting
        await self.check_rate_limit()
        
        # Ensure we're authenticated
        await self.ensure_authenticated()
        
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "X-Dealer-ID": str(self.dealer_id)
        }
        
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                self.total_requests += 1
                
                async with self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    headers=headers
                ) as response:
                    
                    # Handle authentication errors
                    if response.status == 401:
                        logger.warning(f"CDK request got 401, attempting re-authentication (attempt {attempt + 1})")
                        await self.authenticate()
                        headers["Authorization"] = f"Bearer {self.access_token}"
                        continue
                    
                    # Handle rate limiting
                    if response.status == 429:
                        retry_after = int(response.headers.get("Retry-After", 60))
                        if attempt < max_retries - 1:
                            logger.warning(f"CDK rate limited, waiting {retry_after}s (attempt {attempt + 1})")
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            raise CDKRateLimitError(f"CDK rate limit exceeded after {max_retries} attempts")
                    
                    # Handle other errors
                    if response.status >= 400:
                        error_text = await response.text()
                        self.failed_requests += 1
                        raise Exception(f"CDK API error {response.status}: {error_text}")
                    
                    # Success
                    return await response.json()
                    
            except Exception as e:
                last_exception = e
                if attempt == max_retries - 1:
                    break
                
                # Exponential backoff for retries
                wait_time = 2 ** attempt
                logger.warning(f"CDK request failed (attempt {attempt + 1}), retrying in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
        
        # All retries failed
        self.failed_requests += 1
        raise Exception(f"CDK request failed after {max_retries} attempts: {last_exception}")

    async def get_inventory(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Vehicle]:
        """
        Get vehicle inventory from CDK Global.
        
        Args:
            filters: Dictionary of filters (make, model, year, etc.)
            limit: Maximum number of vehicles to return
            offset: Number of vehicles to skip for pagination
            
        Returns:
            List of Vehicle objects
        """
        try:
            params = {
                "limit": min(limit, 500),  # CDK max limit
                "offset": offset
            }
            
            # Add filters
            if filters:
                if "make" in filters:
                    params["make"] = filters["make"]
                if "model" in filters:
                    params["model"] = filters["model"]
                if "year" in filters:
                    params["year"] = filters["year"]
                if "status" in filters:
                    params["status"] = filters["status"]
                if "category" in filters:
                    params["category"] = filters["category"]  # new, used, certified
            
            # Make request to CDK inventory endpoint
            response_data = await self.make_authenticated_request(
                method="GET",
                endpoint="/v1/inventory/vehicles",
                params=params
            )
            
            # Parse response into Vehicle objects
            vehicles = []
            for item in response_data.get("data", []):
                try:
                    vehicle = Vehicle(
                        vin=item["vin"],
                        make=item["make"],
                        model=item["model"],
                        year=int(item["year"]),
                        trim=item.get("trim", ""),
                        color=item.get("color", ""),
                        mileage=item.get("mileage", 0),
                        price=float(item.get("price", 0)),
                        status=item.get("status", "available"),
                        category=item.get("category", "unknown"),
                        features=item.get("features", []),
                        images=item.get("images", []),
                        location=item.get("location", ""),
                        dealer_id=str(self.dealer_id),
                        last_updated=datetime.fromisoformat(
                            item.get("updated_at", datetime.now().isoformat())
                        )
                    )
                    vehicles.append(vehicle)
                except Exception as e:
                    logger.warning(f"Failed to parse CDK vehicle {item.get('vin', 'unknown')}: {e}")
                    continue
            
            logger.info(f"Retrieved {len(vehicles)} vehicles from CDK inventory")
            return vehicles
            
        except Exception as e:
            logger.error(f"CDK inventory retrieval failed: {e}")
            return []

    async def get_vehicle_details(self, vin: str) -> Optional[Vehicle]:
        """
        Get detailed information for a specific vehicle by VIN.
        
        Args:
            vin: Vehicle Identification Number
            
        Returns:
            Vehicle object or None if not found
        """
        try:
            if not vin or len(vin) != 17:
                logger.warning(f"Invalid VIN provided: {vin}")
                return None
            
            # Make request to CDK vehicle details endpoint
            response_data = await self.make_authenticated_request(
                method="GET",
                endpoint=f"/v1/inventory/vehicles/{vin}"
            )
            
            item = response_data.get("data", {})
            if not item:
                logger.info(f"Vehicle {vin} not found in CDK")
                return None
            
            # Create detailed Vehicle object
            vehicle = Vehicle(
                vin=item["vin"],
                make=item["make"],
                model=item["model"],
                year=int(item["year"]),
                trim=item.get("trim", ""),
                color=item.get("color", ""),
                mileage=item.get("mileage", 0),
                price=float(item.get("price", 0)),
                status=item.get("status", "available"),
                category=item.get("category", "unknown"),
                features=item.get("features", []),
                images=item.get("images", []),
                location=item.get("location", ""),
                dealer_id=str(self.dealer_id),
                last_updated=datetime.fromisoformat(
                    item.get("updated_at", datetime.now().isoformat())
                ),
                # Detailed fields
                engine=item.get("engine", ""),
                transmission=item.get("transmission", ""),
                drivetrain=item.get("drivetrain", ""),
                fuel_type=item.get("fuel_type", ""),
                mpg_city=item.get("mpg_city", 0),
                mpg_highway=item.get("mpg_highway", 0),
                safety_rating=item.get("safety_rating", ""),
                warranty=item.get("warranty", {}),
                history_report=item.get("history_report", {}),
            )
            
            logger.info(f"Retrieved detailed information for vehicle {vin}")
            return vehicle
            
        except Exception as e:
            logger.error(f"CDK vehicle details retrieval failed for {vin}: {e}")
            return None

    async def get_service_history(self, vin: str) -> List[Dict[str, Any]]:
        """
        Get service history for a specific vehicle by VIN.
        
        Args:
            vin: Vehicle Identification Number
            
        Returns:
            List of service records
        """
        try:
            if not vin or len(vin) != 17:
                logger.warning(f"Invalid VIN provided: {vin}")
                return []
            
            # Make request to CDK service history endpoint
            response_data = await self.make_authenticated_request(
                method="GET",
                endpoint=f"/v1/service/vehicles/{vin}/history"
            )
            
            service_records = []
            for record in response_data.get("data", []):
                try:
                    service_record = {
                        "service_id": record["id"],
                        "vin": vin,
                        "date": record["date"],
                        "mileage": record.get("mileage", 0),
                        "type": record.get("type", "unknown"),
                        "description": record.get("description", ""),
                        "parts_used": record.get("parts", []),
                        "labor_hours": record.get("labor_hours", 0),
                        "cost": float(record.get("cost", 0)),
                        "technician": record.get("technician", ""),
                        "warranty_work": record.get("warranty_work", False),
                        "dealer_id": str(self.dealer_id)
                    }
                    service_records.append(service_record)
                except Exception as e:
                    logger.warning(f"Failed to parse CDK service record: {e}")
                    continue
            
            logger.info(f"Retrieved {len(service_records)} service records for vehicle {vin}")
            return service_records
            
        except Exception as e:
            logger.error(f"CDK service history retrieval failed for {vin}: {e}")
            return []

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on CDK API connectivity.
        
        Returns:
            Dictionary with health status information
        """
        health = {
            "service": "cdk_global",
            "status": "unknown",
            "timestamp": int(time.time()),
            "checks": {}
        }
        
        try:
            # Check authentication
            await self.ensure_authenticated()
            health["checks"]["authentication"] = "healthy"
            
            # Test API connectivity with a simple request
            await self.make_authenticated_request(
                method="GET",
                endpoint="/v1/health",
                max_retries=1
            )
            
            health["checks"]["api_connectivity"] = "healthy"
            health["status"] = "healthy"
            
            # Add performance stats
            success_rate = 1.0 - (self.failed_requests / max(1, self.total_requests))
            health["checks"]["success_rate"] = success_rate
            health["checks"]["total_requests"] = self.total_requests
            health["checks"]["failed_requests"] = self.failed_requests
            health["checks"]["rate_limit_hits"] = self.rate_limit_hits
            
        except CDKAuthenticationError:
            health["checks"]["authentication"] = "failed"
            health["status"] = "unhealthy"
        except Exception as e:
            health["checks"]["api_connectivity"] = f"failed: {str(e)}"
            health["status"] = "degraded"
        
        return health

    async def close(self):
        """Clean up resources."""
        if self.session:
            await self.session.close()
        
        logger.info(
            f"CDK adapter closed - Total requests: {self.total_requests}, "
            f"Failed: {self.failed_requests}, Auth failures: {self.auth_failures}, "
            f"Rate limit hits: {self.rate_limit_hits}"
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get adapter performance statistics."""
        return {
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
            "auth_failures": self.auth_failures,
            "rate_limit_hits": self.rate_limit_hits,
            "success_rate": 1.0 - (self.failed_requests / max(1, self.total_requests)),
            "authenticated": self.access_token is not None,
            "token_expires_at": self.token_expires_at.isoformat() if self.token_expires_at else None,
        }