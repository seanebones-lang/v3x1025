"""
Pydantic models for the Dealership RAG system.
Defines data structures for API requests, responses, and internal data.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Request model for querying the RAG system."""

    query: str = Field(..., description="User's question")
    conversation_id: Optional[str] = Field(
        None, description="Conversation ID for multi-turn context"
    )
    filters: Optional[dict[str, Any]] = Field(None, description="Metadata filters")
    top_k: int = Field(5, description="Number of results to return")
    include_sources: bool = Field(True, description="Include source documents")


class SourceDocument(BaseModel):
    """Represents a source document chunk."""

    id: str
    text: str
    metadata: dict[str, Any]
    score: Optional[float] = Field(None, description="Relevance score")


class QueryResponse(BaseModel):
    """Response model for a RAG query."""

    answer: str
    sources: list[SourceDocument]
    conversation_id: str
    query_time_ms: float
    model_used: str
    intent: Optional[str] = None


class IngestRequest(BaseModel):
    """Request model for ingesting data."""

    source_type: Literal["file", "dms", "url", "text"]
    source_identifier: Optional[str] = None
    content: Optional[str] = None
    metadata: Optional[dict[str, Any]] = Field(default_factory=dict)
    namespace: Optional[str] = "default"


class IngestResponse(BaseModel):
    """Response model for an ingestion request."""

    status: str
    documents_processed: int
    chunks_created: int
    vectors_upserted: int
    processing_time_ms: float
    errors: list[str]


class HealthCheck(BaseModel):
    """Response model for health check."""

    status: str
    timestamp: datetime
    version: str
    services: dict[str, bool]


class SystemMetrics(BaseModel):
    """Response model for system metrics."""

    total_queries: int
    average_latency_ms: float
    cache_hit_rate: float
    error_rate: float
    total_documents: int
    uptime_seconds: float


class ErrorResponse(BaseModel):
    """Standard error response model."""

    detail: str


class VehicleStatus(str, Enum):
    """Vehicle availability status."""
    AVAILABLE = "available"
    SOLD = "sold"
    RESERVED = "reserved"
    IN_TRANSIT = "in_transit"
    SERVICE = "service"


class VehicleCategory(str, Enum):
    """Vehicle category/type."""
    NEW = "new"
    USED = "used"
    CERTIFIED = "certified"
    LEASE_RETURN = "lease_return"


class Vehicle(BaseModel):
    """Enhanced vehicle model with comprehensive dealership data."""
    
    # Basic vehicle information
    vin: str = Field(..., description="Vehicle Identification Number")
    make: str = Field(..., description="Vehicle manufacturer")
    model: str = Field(..., description="Vehicle model")
    year: int = Field(..., description="Vehicle year")
    
    # Physical characteristics
    trim: str = Field(default="", description="Trim level")
    color: str = Field(default="", description="Exterior color")
    interior_color: str = Field(default="", description="Interior color")
    body_style: str = Field(default="", description="Body style (sedan, SUV, etc.)")
    doors: int = Field(default=0, description="Number of doors")
    
    # Performance and specs
    engine: str = Field(default="", description="Engine specification")
    transmission: str = Field(default="", description="Transmission type")
    drivetrain: str = Field(default="", description="Drivetrain (FWD, AWD, etc.)")
    fuel_type: str = Field(default="", description="Fuel type")
    mpg_city: int = Field(default=0, description="City MPG")
    mpg_highway: int = Field(default=0, description="Highway MPG")
    
    # Condition and usage
    mileage: int = Field(default=0, description="Vehicle mileage")
    status: VehicleStatus = Field(default=VehicleStatus.AVAILABLE, description="Availability status")
    category: VehicleCategory = Field(default=VehicleCategory.USED, description="Vehicle category")
    
    # Pricing
    price: float = Field(default=0.0, description="Asking price")
    msrp: float = Field(default=0.0, description="Manufacturer suggested retail price")
    invoice: float = Field(default=0.0, description="Dealer invoice price")
    cost: float = Field(default=0.0, description="Dealer cost")
    
    # Additional information
    features: List[str] = Field(default_factory=list, description="Vehicle features and options")
    images: List[str] = Field(default_factory=list, description="Image URLs")
    location: str = Field(default="", description="Lot location or building")
    
    # Safety and ratings
    safety_rating: str = Field(default="", description="Safety rating")
    
    # Warranty and history
    warranty: Dict[str, Any] = Field(default_factory=dict, description="Warranty information")
    history_report: Dict[str, Any] = Field(default_factory=dict, description="Vehicle history report")
    
    # Dealer and system metadata
    dealer_id: str = Field(..., description="Dealer identifier")
    last_updated: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AgentIntent(BaseModel):
    """Represents the classified intent of a query."""

    intent: str
    confidence: float
    sub_intent: Optional[str] = None
    entities: dict[str, Any]


class DMSConfig(BaseModel):
    """Configuration for a DMS adapter."""

    adapter: str
    api_key: str
    api_url: str


class CustomerQuery(BaseModel):
    """Represents a customer's query and associated data."""

    query: str
    customer_id: Optional[str] = Field(None, description="Customer identifier")
    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique session ID"
    )
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    """Represents a tool call action."""

    tool_name: str
    parameters: dict[str, Any]


class AgentAction(BaseModel):
    """Represents an action taken by the agent."""

    action_type: str  # e.g., "tool_call", "generate_answer"
    tool: Optional[str] = Field(None, description="Tool to use")
    tool_input: Optional[dict[str, Any]] = Field(None, description="Input for the tool")
    log: str


class ErrorDetail(BaseModel):
    """Detailed error information."""
    
    code: str
    message: str
    field: Optional[str] = None
    context: Optional[dict[str, Any]] = None


class StandardErrorResponse(BaseModel):
    """Standardized error response format."""
    
    error: ErrorDetail
    request_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    
    
# Standard error codes
class ErrorCodes:
    # Authentication & Authorization
    INVALID_API_KEY = "AUTH_001"
    MISSING_API_KEY = "AUTH_002" 
    RATE_LIMIT_EXCEEDED = "AUTH_003"
    
    # Input Validation
    INVALID_REQUEST_FORMAT = "VAL_001"
    MISSING_REQUIRED_FIELD = "VAL_002"
    INVALID_FIELD_VALUE = "VAL_003"
    
    # System Errors
    SERVICE_UNAVAILABLE = "SYS_001"
    TIMEOUT_ERROR = "SYS_002"
    EXTERNAL_API_ERROR = "SYS_003"
    
    # Business Logic
    QUERY_PROCESSING_FAILED = "BIZ_001"
    DOCUMENT_INGESTION_FAILED = "BIZ_002"
    DMS_INTEGRATION_ERROR = "BIZ_003"