"""
Production Reynolds & Reynolds DMS adapter with ERA-IGNITE API.
Implements secure authentication, MFA support, and comprehensive error handling.
"""

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp
from aiohttp import ClientSession, ClientTimeout

from src.config import get_config
from src.models import Vehicle
from .base import BaseDMSAdapter

logger = logging.getLogger(__name__)


class ReynoldsAuthenticationError(Exception):
    """Reynolds authentication-specific errors."""
    pass


class ReynoldsRateLimitError(Exception):
    """Reynolds rate limiting errors."""
    pass


class ReynoldsAdapter(BaseDMSAdapter):
    """
    Production Reynolds & Reynolds adapter using ERA-IGNITE DMS.
    
    Implements API key authentication with MFA support, rate limiting, and comprehensive error handling.
    """

    def __init__(self):
        self.config = get_config()
        self.base_url = "https://api.reyrey.com/v2"
        
        # Authentication credentials
        self.api_key = self.config.reynolds_api_key
        self.dealer_code = self.config.reynolds_dealer_code
        self.mfa_token = self.config.reynolds_mfa_token  # For MFA if required
        
        # Session management
        self.session_token: Optional[str] = None
        self.session_expires_at: Optional[datetime] = None
        
        # Rate limiting (Reynolds allows 500 requests per 5 minutes)
        self.rate_limit = 500
        self.rate_window = 300  # 5 minutes
        self.request_timestamps: List[float] = []
        
        # HTTP session
        self.session: Optional[ClientSession] = None
        
        # Performance tracking
        self.total_requests = 0
        self.failed_requests = 0
        self.auth_failures = 0
        self.rate_limit_hits = 0
        
    async def initialize(self):
        """Initialize the Reynolds adapter with authentication."""
        if not self.api_key or not self.dealer_code:
            raise ReynoldsAuthenticationError(
                "Reynolds credentials not configured - check REYNOLDS_API_KEY and REYNOLDS_DEALER_CODE environment variables"
            )
        
        # Create HTTP session with proper configuration
        timeout = ClientTimeout(total=30, connect=10)
        self.session = ClientSession(
            timeout=timeout,
            headers={
                "User-Agent": "Blue1-RAG-System/1.0",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Reynolds-Client": "Blue1-RAG"
            }
        )
        
        # Authenticate
        await self.authenticate()
        logger.info("Reynolds adapter initialized successfully")

    def _generate_signature(self, timestamp: str, method: str, endpoint: str) -> str:
        """
        Generate API signature for Reynolds authentication.
        
        Args:
            timestamp: Unix timestamp as string
            method: HTTP method
            endpoint: API endpoint path
            
        Returns:
            HMAC signature for authentication
        """
        import hmac
        
        # Create signature string
        signature_string = f"{timestamp}{method.upper()}{endpoint}{self.dealer_code}"
        
        # Generate HMAC-SHA256 signature
        signature = hmac.new(
            self.api_key.encode('utf-8'),
            signature_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature

    async def authenticate(self) -> None:
        """
        Perform Reynolds API authentication with signature-based auth.
        
        Raises:
            ReynoldsAuthenticationError: If authentication fails
        """
        try:
            timestamp = str(int(time.time()))
            endpoint = "/auth/session"
            signature = self._generate_signature(timestamp, "POST", endpoint)
            
            auth_payload = {
                "dealer_code": self.dealer_code,
                "timestamp": timestamp,
                "signature": signature
            }
            
            # Add MFA token if configured
            if self.mfa_token:
                auth_payload["mfa_token"] = self.mfa_token
            
            headers = {
                "X-Reynolds-Dealer-Code": self.dealer_code,
                "X-Reynolds-Timestamp": timestamp,
                "X-Reynolds-Signature": signature
            }
            
            async with self.session.post(
                f"{self.base_url}{endpoint}",
                json=auth_payload,
                headers=headers
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    self.auth_failures += 1
                    
                    if response.status == 401:
                        raise ReynoldsAuthenticationError(
                            f"Reynolds authentication failed - invalid credentials: {error_text}"
                        )
                    elif response.status == 423:
                        raise ReynoldsAuthenticationError(
                            "Reynolds account locked - MFA required or too many failed attempts"
                        )
                    else:
                        raise ReynoldsAuthenticationError(
                            f"Reynolds authentication failed with status {response.status}: {error_text}"
                        )
                
                auth_data = await response.json()
                
                # Extract session token
                self.session_token = auth_data.get("session_token")
                expires_in = auth_data.get("expires_in", 3600)
                
                if not self.session_token:
                    raise ReynoldsAuthenticationError("No session token received from Reynolds")
                
                # Calculate expiration time with 5-minute buffer
                self.session_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)
                
                logger.info(f"Reynolds authentication successful, session expires at {self.session_expires_at}")
                
        except Exception as e:
            if isinstance(e, ReynoldsAuthenticationError):
                raise
            raise ReynoldsAuthenticationError(f"Reynolds authentication failed: {str(e)}")

    async def ensure_authenticated(self) -> None:
        """Ensure we have a valid session token, refreshing if necessary."""
        if not self.session_token or not self.session_expires_at:
            await self.authenticate()
            return
        
        # Check if session is about to expire
        if datetime.now() >= self.session_expires_at:
            logger.info("Reynolds session expired, refreshing...")
            await self.authenticate()

    async def check_rate_limit(self) -> None:
        """
        Check and enforce rate limiting.
        
        Raises:
            ReynoldsRateLimitError: If rate limit would be exceeded
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
            
            raise ReynoldsRateLimitError(
                f"Reynolds rate limit exceeded. Wait {wait_time:.0f} seconds before next request."
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
        Make authenticated request to Reynolds API with comprehensive error handling.
        
        Args:
            method: HTTP method
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON payload
            max_retries: Maximum retry attempts
            
        Returns:
            JSON response data
            
        Raises:
            ReynoldsAuthenticationError: If authentication fails
            ReynoldsRateLimitError: If rate limited
        """
        if not self.session:
            raise ReynoldsAuthenticationError("Reynolds adapter not initialized")
        
        # Check rate limiting
        await self.check_rate_limit()
        
        # Ensure we're authenticated
        await self.ensure_authenticated()
        
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.session_token}",
            "X-Reynolds-Dealer-Code": self.dealer_code
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
                        logger.warning(f"Reynolds request got 401, attempting re-authentication (attempt {attempt + 1})")
                        await self.authenticate()
                        headers["Authorization"] = f"Bearer {self.session_token}"
                        continue
                    
                    # Handle rate limiting
                    if response.status == 429:
                        retry_after = int(response.headers.get("Retry-After", 60))
                        if attempt < max_retries - 1:
                            logger.warning(f"Reynolds rate limited, waiting {retry_after}s (attempt {attempt + 1})")
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            raise ReynoldsRateLimitError(f"Reynolds rate limit exceeded after {max_retries} attempts")
                    
                    # Handle other errors
                    if response.status >= 400:
                        error_text = await response.text()
                        self.failed_requests += 1
                        raise Exception(f"Reynolds API error {response.status}: {error_text}")
                    
                    # Success
                    return await response.json()
                    
            except Exception as e:
                last_exception = e
                if attempt == max_retries - 1:
                    break
                
                # Exponential backoff for retries
                wait_time = 2 ** attempt
                logger.warning(f"Reynolds request failed (attempt {attempt + 1}), retrying in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
        
        # All retries failed
        self.failed_requests += 1
        raise Exception(f"Reynolds request failed after {max_retries} attempts: {last_exception}")

    async def get_inventory(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Vehicle]:
        """
        Get vehicle inventory from Reynolds ERA-IGNITE.
        
        Args:
            filters: Dictionary of filters (make, model, year, etc.)
            limit: Maximum number of vehicles to return
            offset: Number of vehicles to skip for pagination
            
        Returns:
            List of Vehicle objects
        """
        try:
            params = {
                "limit": min(limit, 200),  # Reynolds max limit
                "offset": offset,
                "dealer_code": self.dealer_code
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
                if "type" in filters:
                    params["type"] = filters["type"]  # new, used, lease_return
            
            # Make request to Reynolds inventory endpoint
            response_data = await self.make_authenticated_request(
                method="GET",
                endpoint="/inventory/vehicles",
                params=params
            )
            
            # Parse response into Vehicle objects
            vehicles = []
            for item in response_data.get("vehicles", []):
                try:
                    vehicle = Vehicle(
                        vin=item["vin"],
                        make=item["make"],
                        model=item["model"],
                        year=int(item["model_year"]),
                        trim=item.get("trim_level", ""),
                        color=item.get("exterior_color", ""),
                        mileage=item.get("odometer", 0),
                        price=float(item.get("asking_price", 0)),
                        status=item.get("status", "available"),
                        category=item.get("type", "unknown"),
                        features=item.get("options", []),
                        images=item.get("images", []),
                        location=item.get("lot_location", ""),
                        dealer_id=self.dealer_code,
                        last_updated=datetime.fromisoformat(
                            item.get("last_modified", datetime.now().isoformat())
                        )
                    )
                    vehicles.append(vehicle)
                except Exception as e:
                    logger.warning(f"Failed to parse Reynolds vehicle {item.get('vin', 'unknown')}: {e}")
                    continue
            
            logger.info(f"Retrieved {len(vehicles)} vehicles from Reynolds inventory")
            return vehicles
            
        except Exception as e:
            logger.error(f"Reynolds inventory retrieval failed: {e}")
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
            
            # Make request to Reynolds vehicle details endpoint
            response_data = await self.make_authenticated_request(
                method="GET",
                endpoint=f"/inventory/vehicles/{vin}",
                params={"dealer_code": self.dealer_code}
            )
            
            item = response_data.get("vehicle", {})
            if not item:
                logger.info(f"Vehicle {vin} not found in Reynolds")
                return None
            
            # Create detailed Vehicle object
            vehicle = Vehicle(
                vin=item["vin"],
                make=item["make"],
                model=item["model"],
                year=int(item["model_year"]),
                trim=item.get("trim_level", ""),
                color=item.get("exterior_color", ""),
                mileage=item.get("odometer", 0),
                price=float(item.get("asking_price", 0)),
                status=item.get("status", "available"),
                category=item.get("type", "unknown"),
                features=item.get("options", []),
                images=item.get("images", []),
                location=item.get("lot_location", ""),
                dealer_id=self.dealer_code,
                last_updated=datetime.fromisoformat(
                    item.get("last_modified", datetime.now().isoformat())
                ),
                # Detailed fields
                engine=item.get("engine", ""),
                transmission=item.get("transmission", ""),
                drivetrain=item.get("drivetrain", ""),
                fuel_type=item.get("fuel_type", ""),
                mpg_city=item.get("mpg_city", 0),
                mpg_highway=item.get("mpg_highway", 0),
                interior_color=item.get("interior_color", ""),
                body_style=item.get("body_style", ""),
                doors=item.get("doors", 0),
                msrp=float(item.get("msrp", 0)),
                invoice=float(item.get("invoice", 0)),
                cost=float(item.get("cost", 0)),
            )
            
            logger.info(f"Retrieved detailed information for vehicle {vin}")
            return vehicle
            
        except Exception as e:
            logger.error(f"Reynolds vehicle details retrieval failed for {vin}: {e}")
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
            
            # Make request to Reynolds service history endpoint
            response_data = await self.make_authenticated_request(
                method="GET",
                endpoint=f"/service/vehicles/{vin}/history",
                params={"dealer_code": self.dealer_code}
            )
            
            service_records = []
            for record in response_data.get("service_records", []):
                try:
                    service_record = {
                        "service_id": record["repair_order_number"],
                        "vin": vin,
                        "date": record["service_date"],
                        "mileage": record.get("mileage_in", 0),
                        "type": record.get("service_type", "unknown"),
                        "description": record.get("customer_concern", ""),
                        "work_performed": record.get("work_performed", ""),
                        "parts_used": record.get("parts", []),
                        "labor_hours": record.get("total_labor_hours", 0),
                        "parts_cost": float(record.get("parts_total", 0)),
                        "labor_cost": float(record.get("labor_total", 0)),
                        "total_cost": float(record.get("total_amount", 0)),
                        "technician": record.get("technician_name", ""),
                        "service_advisor": record.get("service_advisor", ""),
                        "warranty_work": record.get("warranty_flag", False),
                        "customer_pay": record.get("customer_pay_flag", True),
                        "dealer_id": self.dealer_code
                    }
                    service_records.append(service_record)
                except Exception as e:
                    logger.warning(f"Failed to parse Reynolds service record: {e}")
                    continue
            
            logger.info(f"Retrieved {len(service_records)} service records for vehicle {vin}")
            return service_records
            
        except Exception as e:
            logger.error(f"Reynolds service history retrieval failed for {vin}: {e}")
            return []

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on Reynolds API connectivity.
        
        Returns:
            Dictionary with health status information
        """
        health = {
            "service": "reynolds_reynolds",
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
                endpoint="/system/status",
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
            
        except ReynoldsAuthenticationError:
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
            f"Reynolds adapter closed - Total requests: {self.total_requests}, "
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
            "authenticated": self.session_token is not None,
            "session_expires_at": self.session_expires_at.isoformat() if self.session_expires_at else None,
        }