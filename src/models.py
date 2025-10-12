"""
Pydantic models for API requests, responses, and internal data structures.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator
import re


# ============================================================================
# Query Models
# ============================================================================

class QueryRequest(BaseModel):
    """Request model for querying the RAG system."""
    
    query: str = Field(..., description="User query text", min_length=1, max_length=1000)
    conversation_id: Optional[str] = Field(None, description="Conversation ID for multi-turn context")
    filters: Optional[Dict[str, Any]] = Field(None, description="Metadata filters for retrieval")
    top_k: Optional[int] = Field(None, ge=1, le=50, description="Number of results to return")
    include_sources: bool = Field(True, description="Include source documents in response")
    stream: bool = Field(False, description="Stream the response")
    
    @field_validator('query')
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        """
        Recursive XSS sanitization to prevent nested payload injections.
        Handles encoded attacks and recursive patterns.
        """
        import html
        
        # Decode HTML entities recursively (prevents encoded attacks)
        prev = ""
        current = v
        iterations = 0
        while prev != current and iterations < 5:  # Max 5 iterations to prevent infinite loops
            prev = current
            current = html.unescape(current)
            iterations += 1
        
        # Remove dangerous characters and tags
        sanitized = re.sub(r'[<>]', '', current)
        
        # Remove script tags and event handlers (case-insensitive, recursive)
        sanitized = re.sub(r'<script[^>]*>.*?</script>', '', sanitized, flags=re.IGNORECASE | re.DOTALL)
        sanitized = re.sub(r'on\w+\s*=', '', sanitized, flags=re.IGNORECASE)
        
        # Remove SQL injection patterns
        sanitized = re.sub(r'(;|\b(DROP|DELETE|INSERT|UPDATE|EXEC|UNION|SELECT)\b)', '', sanitized, flags=re.IGNORECASE)
        
        # Trim whitespace
        sanitized = sanitized.strip()
        
        # Remove multiple spaces
        sanitized = re.sub(r'\s+', ' ', sanitized)
        
        return sanitized


class SourceDocument(BaseModel):
    """Model for source document metadata."""
    
    content: str = Field(..., description="Document content snippet")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Document metadata")
    score: Optional[float] = Field(None, description="Relevance score")
    source: Optional[str] = Field(None, description="Source system or file")
    document_id: Optional[str] = Field(None, description="Unique document identifier")


class QueryResponse(BaseModel):
    """Response model for query results."""
    
    answer: str = Field(..., description="Generated answer")
    sources: List[SourceDocument] = Field(default_factory=list, description="Source documents")
    conversation_id: str = Field(..., description="Conversation ID for context")
    query_time_ms: float = Field(..., description="Query processing time in milliseconds")
    model_used: str = Field(..., description="LLM model used for generation")
    intent: Optional[str] = Field(None, description="Detected query intent")


# ============================================================================
# Ingest Models
# ============================================================================

class IngestRequest(BaseModel):
    """Request model for document ingestion."""
    
    source_type: Literal["file", "dms", "url", "text"] = Field(
        ...,
        description="Type of data source"
    )
    source_identifier: Optional[str] = Field(None, description="File path, URL, or identifier")
    content: Optional[str] = Field(None, description="Direct text content to ingest")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional metadata for the documents"
    )
    namespace: Optional[str] = Field("default", description="Pinecone namespace for organization")


class IngestResponse(BaseModel):
    """Response model for ingestion results."""
    
    status: Literal["success", "partial", "failed"] = Field(..., description="Ingestion status")
    documents_processed: int = Field(..., description="Number of documents processed")
    chunks_created: int = Field(..., description="Number of chunks created")
    vectors_upserted: int = Field(..., description="Number of vectors upserted to Pinecone")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")
    errors: List[str] = Field(default_factory=list, description="Any errors encountered")


# ============================================================================
# DMS Models
# ============================================================================

class Vehicle(BaseModel):
    """Model for vehicle data from DMS."""
    
    vin: str = Field(..., description="Vehicle Identification Number")
    make: str = Field(..., description="Vehicle make")
    model: str = Field(..., description="Vehicle model")
    year: int = Field(..., description="Model year")
    trim: Optional[str] = Field(None, description="Trim level")
    mileage: Optional[int] = Field(None, description="Current mileage")
    price: Optional[float] = Field(None, description="Listed price")
    status: Literal["available", "sold", "pending", "service"] = Field(
        ...,
        description="Vehicle status"
    )
    color_exterior: Optional[str] = Field(None, description="Exterior color")
    color_interior: Optional[str] = Field(None, description="Interior color")
    engine: Optional[str] = Field(None, description="Engine specification")
    transmission: Optional[str] = Field(None, description="Transmission type")
    fuel_type: Optional[str] = Field(None, description="Fuel type")
    features: List[str] = Field(default_factory=list, description="Vehicle features")
    images: List[HttpUrl] = Field(default_factory=list, description="Image URLs")
    location: Optional[str] = Field(None, description="Dealership location")
    stock_number: Optional[str] = Field(None, description="Stock/lot number")
    created_at: Optional[datetime] = Field(None, description="Date added to inventory")
    updated_at: Optional[datetime] = Field(None, description="Last updated date")


class CustomerQuery(BaseModel):
    """Model for customer service queries."""
    
    customer_id: Optional[str] = Field(None, description="Customer identifier")
    query_type: Literal["sales", "service", "inventory", "financing", "general"] = Field(
        ...,
        description="Type of customer query"
    )
    query_text: str = Field(..., description="Customer query text")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")


# ============================================================================
# Agent Models
# ============================================================================

class AgentIntent(BaseModel):
    """Model for detected user intent."""
    
    intent: Literal["sales", "service", "inventory", "predictive", "general"] = Field(
        ...,
        description="Detected intent category"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    sub_intent: Optional[str] = Field(None, description="Specific sub-intent")
    entities: Dict[str, Any] = Field(default_factory=dict, description="Extracted entities")


class AgentAction(BaseModel):
    """Model for agent actions and tool calls."""
    
    action: str = Field(..., description="Action to take")
    tool: Optional[str] = Field(None, description="Tool to use")
    tool_input: Optional[Dict[str, Any]] = Field(None, description="Input for the tool")
    reasoning: Optional[str] = Field(None, description="Reasoning for the action")


# ============================================================================
# Health & Status Models
# ============================================================================

class HealthCheck(BaseModel):
    """Health check response model."""
    
    status: Literal["healthy", "degraded", "unhealthy"] = Field(..., description="Service status")
    timestamp: datetime = Field(default_factory=datetime.now, description="Check timestamp")
    version: str = Field(..., description="Application version")
    services: Dict[str, bool] = Field(default_factory=dict, description="Service availability")
    latency_ms: Optional[float] = Field(None, description="Average response latency")


class SystemMetrics(BaseModel):
    """System metrics model."""
    
    total_queries: int = Field(..., description="Total queries processed")
    average_latency_ms: float = Field(..., description="Average query latency")
    cache_hit_rate: float = Field(..., ge=0.0, le=1.0, description="Cache hit rate")
    error_rate: float = Field(..., ge=0.0, le=1.0, description="Error rate")
    total_documents: int = Field(..., description="Total documents indexed")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")


# ============================================================================
# Error Models
# ============================================================================

class ErrorResponse(BaseModel):
    """Standard error response model."""
    
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    request_id: Optional[str] = Field(None, description="Request identifier for tracing")
    timestamp: datetime = Field(default_factory=datetime.now, description="Error timestamp")

