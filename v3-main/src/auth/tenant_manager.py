"""
Multi-tenant authentication and authorization system for enterprise RAG.
Handles dealership group isolation, role-based access control, and API key management.
"""

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

import jwt
import redis.asyncio as redis
from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from src.config import get_config

logger = logging.getLogger(__name__)


class TenantInfo(BaseModel):
    """Tenant information model."""
    tenant_id: str
    name: str
    dealership_group: str
    region: str
    active: bool = True
    tier: str = "standard"  # standard, premium, enterprise
    created_at: datetime
    updated_at: datetime
    
    # Resource limits
    max_queries_per_day: int = 10000
    max_documents: int = 100000
    max_concurrent_requests: int = 50
    
    # Feature flags
    features: Set[str] = set()
    
    # Compliance requirements
    data_retention_days: int = 90
    requires_audit_log: bool = True
    pii_masking_enabled: bool = True


class UserRole(BaseModel):
    """User role within a tenant."""
    role_id: str
    name: str
    permissions: Set[str]
    resource_access: Dict[str, Any]


class ApiKey(BaseModel):
    """API key model with usage tracking."""
    key_id: str
    key_hash: str
    tenant_id: str
    name: str
    created_by: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    # Usage limits
    rate_limit_per_minute: int = 100
    daily_quota: int = 10000
    
    # Current usage
    requests_today: int = 0
    last_reset_date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    
    # Permissions
    scopes: Set[str] = set()
    ip_whitelist: List[str] = []
    
    active: bool = True


class TenantManager:
    """Enterprise tenant management with Redis clustering and compliance."""
    
    def __init__(self):
        self.config = get_config()
        self.redis_client: Optional[redis.RedisCluster] = None
        self.jwt_secret = self.config.api_secret_key
        self.jwt_algorithm = "HS256"
        
        # Cache TTLs
        self.tenant_cache_ttl = 3600  # 1 hour
        self.apikey_cache_ttl = 300   # 5 minutes
        self.rate_limit_ttl = 60      # 1 minute
        
        # Permission definitions
        self.permissions = {
            "query:read": "Execute queries",
            "query:advanced": "Advanced query features",
            "documents:read": "Read documents",
            "documents:write": "Upload/modify documents",
            "documents:delete": "Delete documents",
            "analytics:read": "View analytics",
            "admin:tenant": "Manage tenant settings",
            "admin:users": "Manage users and roles",
            "admin:apikeys": "Manage API keys",
        }

    async def initialize(self) -> None:
        """Initialize Redis cluster connection."""
        try:
            # Connect to Redis cluster for high availability
            startup_nodes = [
                {"host": "redis-cluster-0.redis.dealership-rag.svc.cluster.local", "port": 6379},
                {"host": "redis-cluster-1.redis.dealership-rag.svc.cluster.local", "port": 6379},
                {"host": "redis-cluster-2.redis.dealership-rag.svc.cluster.local", "port": 6379},
            ]
            
            self.redis_client = redis.RedisCluster(
                startup_nodes=startup_nodes,
                decode_responses=True,
                skip_full_coverage_check=True,
                health_check_interval=30,
            )
            
            await self.redis_client.ping()
            logger.info("Connected to Redis cluster for tenant management")
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis cluster: {e}")
            raise

    async def create_tenant(
        self,
        name: str,
        dealership_group: str,
        region: str,
        tier: str = "standard",
        **kwargs
    ) -> TenantInfo:
        """Create a new tenant with proper isolation."""
        tenant_id = f"tenant_{uuid4().hex[:12]}"
        
        # Set resource limits based on tier
        tier_limits = {
            "standard": {"queries": 10000, "docs": 100000, "concurrent": 50},
            "premium": {"queries": 50000, "docs": 500000, "concurrent": 200},
            "enterprise": {"queries": 1000000, "docs": 5000000, "concurrent": 1000},
        }
        
        limits = tier_limits.get(tier, tier_limits["standard"])
        
        tenant = TenantInfo(
            tenant_id=tenant_id,
            name=name,
            dealership_group=dealership_group,
            region=region,
            tier=tier,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            max_queries_per_day=limits["queries"],
            max_documents=limits["docs"],
            max_concurrent_requests=limits["concurrent"],
            **kwargs
        )
        
        # Store tenant in Redis with proper indexing
        await self._store_tenant(tenant)
        
        # Create default namespace in Pinecone
        await self._create_tenant_namespace(tenant_id)
        
        logger.info(f"Created tenant {tenant_id} for {dealership_group}")
        return tenant

    async def authenticate_api_key(self, api_key: str) -> tuple[TenantInfo, ApiKey]:
        """Authenticate API key and return tenant + key info."""
        # Hash the key for lookup
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        # Check cache first
        cache_key = f"apikey:{key_hash}"
        cached_data = await self.redis_client.get(cache_key)
        
        if cached_data:
            key_data = json.loads(cached_data)
            api_key_obj = ApiKey(**key_data)
        else:
            # Lookup in persistent storage
            api_key_obj = await self._get_api_key_by_hash(key_hash)
            if not api_key_obj:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid API key"
                )
            
            # Cache for faster subsequent lookups
            await self.redis_client.setex(
                cache_key, 
                self.apikey_cache_ttl, 
                api_key_obj.model_dump_json()
            )
        
        # Check if key is active and not expired
        if not api_key_obj.active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key is inactive"
            )
        
        if api_key_obj.expires_at and datetime.now() > api_key_obj.expires_at:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has expired"
            )
        
        # Get tenant info
        tenant = await self.get_tenant(api_key_obj.tenant_id)
        if not tenant or not tenant.active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant is inactive"
            )
        
        # Check rate limits
        await self._check_rate_limits(api_key_obj)
        
        # Update usage tracking
        await self._update_api_key_usage(api_key_obj)
        
        return tenant, api_key_obj

    async def check_permission(
        self,
        tenant_id: str,
        api_key_id: str,
        permission: str,
        resource: Optional[str] = None
    ) -> bool:
        """Check if API key has specific permission."""
        try:
            # Get API key from cache/storage
            api_key = await self._get_api_key_by_id(api_key_id)
            if not api_key:
                return False
            
            # Check if permission is in key scopes
            if permission not in api_key.scopes and "*" not in api_key.scopes:
                return False
            
            # Additional resource-based checks
            if resource and api_key.scopes != {"*"}:
                # Implement resource-specific permission logic
                pass
            
            return True
            
        except Exception as e:
            logger.error(f"Permission check failed: {e}")
            return False

    async def get_tenant_usage(self, tenant_id: str) -> Dict[str, Any]:
        """Get comprehensive tenant usage statistics."""
        usage_key = f"tenant:usage:{tenant_id}"
        
        # Get current usage from Redis
        usage_data = await self.redis_client.hgetall(usage_key)
        
        return {
            "queries_today": int(usage_data.get("queries_today", 0)),
            "documents_indexed": int(usage_data.get("documents_indexed", 0)),
            "active_api_keys": int(usage_data.get("active_api_keys", 0)),
            "last_query_time": usage_data.get("last_query_time"),
            "concurrent_requests": int(usage_data.get("concurrent_requests", 0)),
        }

    async def enforce_tenant_isolation(
        self,
        tenant_id: str,
        operation: str,
        **context
    ) -> None:
        """Enforce data isolation between tenants."""
        
        # Validate tenant can perform operation
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant not found"
            )
        
        # Check resource limits
        usage = await self.get_tenant_usage(tenant_id)
        
        if operation == "query":
            if usage["queries_today"] >= tenant.max_queries_per_day:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Daily query limit exceeded"
                )
            
            if usage["concurrent_requests"] >= tenant.max_concurrent_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many concurrent requests"
                )
        
        elif operation == "ingest":
            if usage["documents_indexed"] >= tenant.max_documents:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Document limit exceeded"
                )
        
        # Log operation for audit trail
        if tenant.requires_audit_log:
            await self._log_tenant_operation(tenant_id, operation, context)

    async def get_tenant(self, tenant_id: str) -> Optional[TenantInfo]:
        """Get tenant information with caching."""
        cache_key = f"tenant:{tenant_id}"
        
        # Check cache first
        cached_data = await self.redis_client.get(cache_key)
        if cached_data:
            return TenantInfo(**json.loads(cached_data))
        
        # Load from persistent storage
        tenant = await self._load_tenant_from_storage(tenant_id)
        if tenant:
            # Cache for future lookups
            await self.redis_client.setex(
                cache_key,
                self.tenant_cache_ttl,
                tenant.model_dump_json()
            )
        
        return tenant

    async def rotate_api_key(
        self,
        tenant_id: str,
        key_id: str,
        created_by: str
    ) -> tuple[str, ApiKey]:
        """Rotate an API key for security."""
        # Get existing key
        old_key = await self._get_api_key_by_id(key_id)
        if not old_key or old_key.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found"
            )
        
        # Generate new key
        new_key_str = f"rag_{uuid4().hex}"
        new_key_hash = hashlib.sha256(new_key_str.encode()).hexdigest()
        
        # Create new key object with same properties
        new_key = ApiKey(
            key_id=f"key_{uuid4().hex[:12]}",
            key_hash=new_key_hash,
            tenant_id=tenant_id,
            name=f"{old_key.name} (rotated)",
            created_by=created_by,
            created_at=datetime.now(),
            rate_limit_per_minute=old_key.rate_limit_per_minute,
            daily_quota=old_key.daily_quota,
            scopes=old_key.scopes,
            ip_whitelist=old_key.ip_whitelist,
        )
        
        # Store new key and deactivate old one
        await self._store_api_key(new_key)
        old_key.active = False
        await self._store_api_key(old_key)
        
        # Invalidate caches
        await self._invalidate_key_cache(old_key.key_hash)
        
        logger.info(f"Rotated API key {key_id} for tenant {tenant_id}")
        return new_key_str, new_key

    # Internal methods for storage and caching
    async def _store_tenant(self, tenant: TenantInfo) -> None:
        """Store tenant in persistent storage."""
        # This would typically use a database like PostgreSQL
        # For now, we'll use Redis as both cache and storage
        key = f"tenant:storage:{tenant.tenant_id}"
        await self.redis_client.set(key, tenant.model_dump_json())
        
        # Index by dealership group for lookups
        await self.redis_client.sadd(f"dealership:{tenant.dealership_group}", tenant.tenant_id)

    async def _create_tenant_namespace(self, tenant_id: str) -> None:
        """Create isolated namespace for tenant in vector database."""
        # This would create namespace in Pinecone
        logger.info(f"Created namespace for tenant {tenant_id}")

    async def _check_rate_limits(self, api_key: ApiKey) -> None:
        """Check and enforce API key rate limits."""
        current_minute = int(time.time() // 60)
        rate_key = f"rate:{api_key.key_id}:{current_minute}"
        
        # Check current requests in this minute
        current_requests = await self.redis_client.incr(rate_key)
        if current_requests == 1:
            await self.redis_client.expire(rate_key, 60)
        
        if current_requests > api_key.rate_limit_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded"
            )
        
        # Check daily quota
        today = datetime.now().strftime("%Y-%m-%d")
        if api_key.last_reset_date != today:
            api_key.requests_today = 0
            api_key.last_reset_date = today
        
        if api_key.requests_today >= api_key.daily_quota:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Daily quota exceeded"
            )

    async def _update_api_key_usage(self, api_key: ApiKey) -> None:
        """Update API key usage statistics."""
        api_key.last_used_at = datetime.now()
        api_key.requests_today += 1
        
        # Update in storage (async)
        await self._store_api_key(api_key)

    async def _log_tenant_operation(
        self,
        tenant_id: str,
        operation: str,
        context: Dict[str, Any]
    ) -> None:
        """Log tenant operation for audit trail."""
        audit_log = {
            "timestamp": datetime.now().isoformat(),
            "tenant_id": tenant_id,
            "operation": operation,
            "context": context,
        }
        
        # Store in audit log (would use dedicated audit storage)
        audit_key = f"audit:{tenant_id}:{int(time.time())}"
        await self.redis_client.setex(audit_key, 86400 * 90, json.dumps(audit_log))  # 90 days

    # Placeholder methods for storage operations
    async def _get_api_key_by_hash(self, key_hash: str) -> Optional[ApiKey]:
        """Get API key by hash from storage."""
        # Implementation would query database
        return None

    async def _get_api_key_by_id(self, key_id: str) -> Optional[ApiKey]:
        """Get API key by ID from storage."""
        # Implementation would query database
        return None

    async def _store_api_key(self, api_key: ApiKey) -> None:
        """Store API key in persistent storage."""
        # Implementation would use database
        pass

    async def _load_tenant_from_storage(self, tenant_id: str) -> Optional[TenantInfo]:
        """Load tenant from persistent storage."""
        # Implementation would query database
        return None

    async def _invalidate_key_cache(self, key_hash: str) -> None:
        """Invalidate API key cache."""
        cache_key = f"apikey:{key_hash}"
        await self.redis_client.delete(cache_key)