"""
Production OpenTelemetry setup for comprehensive observability.
Implements distributed tracing, metrics, and logging for the Blue1 RAG system.
"""

import logging
import os
import time
from typing import Any, Dict, Optional

from fastapi import Request, Response
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricExporter
from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

from src.config import get_config

logger = logging.getLogger(__name__)


class TelemetryManager:
    """
    Production telemetry manager for comprehensive observability.
    """

    def __init__(self):
        self.config = get_config()
        
        # Resource identification
        self.resource = Resource.create({
            "service.name": "blue1-rag-system",
            "service.version": "1.0.0",
            "service.instance.id": f"blue1-{os.getpid()}",
            "deployment.environment": self.config.environment,
            "telemetry.sdk.language": "python",
            "telemetry.sdk.name": "opentelemetry",
        })
        
        # Tracer and meter instances
        self.tracer_provider: Optional[TracerProvider] = None
        self.meter_provider: Optional[MeterProvider] = None
        self.tracer = None
        self.meter = None
        
        # Metrics instruments
        self.request_counter = None
        self.request_duration = None
        self.active_requests = None
        self.error_counter = None
        self.rag_query_duration = None
        self.rag_query_counter = None
        self.embedding_duration = None
        self.vector_search_duration = None
        self.keyword_search_duration = None
        self.dms_request_duration = None
        self.elasticsearch_query_duration = None
        
        # Application-specific metrics
        self.documents_indexed = None
        self.cache_hits = None
        self.cache_misses = None
        self.model_inference_duration = None

    def initialize(self) -> None:
        """Initialize OpenTelemetry with production configuration."""
        try:
            self._setup_tracing()
            self._setup_metrics()
            self._setup_instrumentation()
            self._create_custom_metrics()
            
            logger.info("OpenTelemetry telemetry initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize OpenTelemetry: {e}")
            raise

    def _setup_tracing(self) -> None:
        """Configure distributed tracing with OTLP exporter."""
        try:
            # Create tracer provider with sampling
            sampling_ratio = 0.1 if self.config.is_production else 1.0  # 10% sampling in prod
            sampler = TraceIdRatioBased(sampling_ratio)
            
            self.tracer_provider = TracerProvider(
                resource=self.resource,
                sampler=sampler,
            )
            
            # Configure span processors
            if self.config.otlp_endpoint:
                # OTLP exporter for production (Jaeger, DataDog, etc.)
                otlp_exporter = OTLPSpanExporter(
                    endpoint=self.config.otlp_endpoint,
                    headers={"authorization": f"Bearer {self.config.otlp_token}"} if self.config.otlp_token else {},
                    insecure=not self.config.otlp_secure,
                )
                span_processor = BatchSpanProcessor(
                    otlp_exporter,
                    max_queue_size=2048,
                    export_timeout_millis=30000,
                    max_export_batch_size=512,
                )
                self.tracer_provider.add_span_processor(span_processor)
            
            # Console exporter for development
            if self.config.is_development:
                console_processor = BatchSpanProcessor(ConsoleSpanExporter())
                self.tracer_provider.add_span_processor(console_processor)
            
            # Set global tracer provider
            trace.set_tracer_provider(self.tracer_provider)
            self.tracer = trace.get_tracer(__name__)
            
            logger.info(f"Tracing initialized with {sampling_ratio*100}% sampling rate")
            
        except Exception as e:
            logger.error(f"Failed to setup tracing: {e}")
            raise

    def _setup_metrics(self) -> None:
        """Configure metrics collection with Prometheus and OTLP exporters."""
        try:
            # Prometheus exporter for metrics scraping
            prometheus_exporter = PrometheusMetricExporter(port=8001)
            prometheus_reader = PeriodicExportingMetricReader(
                prometheus_exporter,
                export_interval_millis=5000,  # 5 seconds
            )
            
            # OTLP exporter for centralized metrics
            readers = [prometheus_reader]
            
            if self.config.otlp_endpoint:
                otlp_metric_exporter = OTLPMetricExporter(
                    endpoint=self.config.otlp_metrics_endpoint or self.config.otlp_endpoint,
                    headers={"authorization": f"Bearer {self.config.otlp_token}"} if self.config.otlp_token else {},
                    insecure=not self.config.otlp_secure,
                )
                otlp_reader = PeriodicExportingMetricReader(
                    otlp_metric_exporter,
                    export_interval_millis=10000,  # 10 seconds
                )
                readers.append(otlp_reader)
            
            # Create meter provider
            self.meter_provider = MeterProvider(
                resource=self.resource,
                metric_readers=readers,
            )
            
            # Set global meter provider
            metrics.set_meter_provider(self.meter_provider)
            self.meter = metrics.get_meter(__name__)
            
            logger.info("Metrics initialized with Prometheus and OTLP exporters")
            
        except Exception as e:
            logger.error(f"Failed to setup metrics: {e}")
            raise

    def _setup_instrumentation(self) -> None:
        """Configure automatic instrumentation for frameworks and libraries."""
        try:
            # HTTP instrumentation
            HTTPXInstrumentor().instrument()
            RequestsInstrumentor().instrument()
            
            # Redis instrumentation
            RedisInstrumentor().instrument()
            
            # Asyncio instrumentation
            AsyncioInstrumentor().instrument()
            
            # Logging instrumentation
            LoggingInstrumentor().instrument(
                set_logging_format=True,
                log_level=logging.INFO,
            )
            
            logger.info("Automatic instrumentation configured")
            
        except Exception as e:
            logger.error(f"Failed to setup instrumentation: {e}")
            raise

    def _create_custom_metrics(self) -> None:
        """Create custom metrics for application-specific monitoring."""
        if not self.meter:
            return
        
        try:
            # HTTP metrics
            self.request_counter = self.meter.create_counter(
                name="http_requests_total",
                description="Total number of HTTP requests",
                unit="1",
            )
            
            self.request_duration = self.meter.create_histogram(
                name="http_request_duration_seconds",
                description="Duration of HTTP requests",
                unit="s",
            )
            
            self.active_requests = self.meter.create_up_down_counter(
                name="http_active_requests",
                description="Number of active HTTP requests",
                unit="1",
            )
            
            self.error_counter = self.meter.create_counter(
                name="application_errors_total",
                description="Total number of application errors",
                unit="1",
            )
            
            # RAG system metrics
            self.rag_query_duration = self.meter.create_histogram(
                name="rag_query_duration_seconds",
                description="Duration of RAG query processing",
                unit="s",
                buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
            )
            
            self.rag_query_counter = self.meter.create_counter(
                name="rag_queries_total",
                description="Total number of RAG queries",
                unit="1",
            )
            
            # Component-specific metrics
            self.embedding_duration = self.meter.create_histogram(
                name="embedding_duration_seconds",
                description="Duration of embedding generation",
                unit="s",
            )
            
            self.vector_search_duration = self.meter.create_histogram(
                name="vector_search_duration_seconds",
                description="Duration of vector search operations",
                unit="s",
            )
            
            self.keyword_search_duration = self.meter.create_histogram(
                name="keyword_search_duration_seconds",
                description="Duration of keyword search operations",
                unit="s",
            )
            
            self.dms_request_duration = self.meter.create_histogram(
                name="dms_request_duration_seconds",
                description="Duration of DMS API requests",
                unit="s",
            )
            
            self.elasticsearch_query_duration = self.meter.create_histogram(
                name="elasticsearch_query_duration_seconds",
                description="Duration of Elasticsearch queries",
                unit="s",
            )
            
            # Application state metrics
            self.documents_indexed = self.meter.create_counter(
                name="documents_indexed_total",
                description="Total number of documents indexed",
                unit="1",
            )
            
            self.cache_hits = self.meter.create_counter(
                name="cache_hits_total",
                description="Total number of cache hits",
                unit="1",
            )
            
            self.cache_misses = self.meter.create_counter(
                name="cache_misses_total",
                description="Total number of cache misses",
                unit="1",
            )
            
            self.model_inference_duration = self.meter.create_histogram(
                name="model_inference_duration_seconds",
                description="Duration of AI model inference",
                unit="s",
            )
            
            logger.info("Custom metrics created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create custom metrics: {e}")
            raise

    def instrument_fastapi_app(self, app) -> None:
        """Instrument FastAPI application with comprehensive monitoring."""
        try:
            # FastAPI automatic instrumentation
            FastAPIInstrumentor.instrument_app(
                app,
                tracer_provider=self.tracer_provider,
                meter_provider=self.meter_provider,
                excluded_urls="health,metrics,docs,redoc,openapi.json",
            )
            
            # Add custom middleware for detailed metrics
            @app.middleware("http")
            async def telemetry_middleware(request: Request, call_next):
                start_time = time.time()
                
                # Increment active requests
                if self.active_requests:
                    self.active_requests.add(1, {"method": request.method, "endpoint": request.url.path})
                
                try:
                    # Process request
                    response = await call_next(request)
                    
                    # Record metrics
                    duration = time.time() - start_time
                    labels = {
                        "method": request.method,
                        "endpoint": request.url.path,
                        "status_code": str(response.status_code),
                    }
                    
                    if self.request_counter:
                        self.request_counter.add(1, labels)
                    
                    if self.request_duration:
                        self.request_duration.record(duration, labels)
                    
                    return response
                    
                except Exception as e:
                    # Record error
                    if self.error_counter:
                        self.error_counter.add(1, {
                            "method": request.method,
                            "endpoint": request.url.path,
                            "error_type": type(e).__name__,
                        })
                    raise
                    
                finally:
                    # Decrement active requests
                    if self.active_requests:
                        self.active_requests.add(-1, {"method": request.method, "endpoint": request.url.path})
            
            logger.info("FastAPI application instrumented successfully")
            
        except Exception as e:
            logger.error(f"Failed to instrument FastAPI app: {e}")
            raise

    def record_rag_query(self, duration: float, query_type: str, success: bool) -> None:
        """Record RAG query metrics."""
        if not self.rag_query_duration or not self.rag_query_counter:
            return
        
        labels = {
            "query_type": query_type,
            "success": str(success),
        }
        
        self.rag_query_duration.record(duration, labels)
        self.rag_query_counter.add(1, labels)

    def record_embedding_operation(self, duration: float, operation: str, success: bool) -> None:
        """Record embedding operation metrics."""
        if not self.embedding_duration:
            return
        
        labels = {
            "operation": operation,
            "success": str(success),
        }
        
        self.embedding_duration.record(duration, labels)

    def record_search_operation(self, duration: float, search_type: str, result_count: int) -> None:
        """Record search operation metrics."""
        labels = {
            "search_type": search_type,
            "result_count_bucket": self._get_count_bucket(result_count),
        }
        
        if search_type == "vector" and self.vector_search_duration:
            self.vector_search_duration.record(duration, labels)
        elif search_type == "keyword" and self.keyword_search_duration:
            self.keyword_search_duration.record(duration, labels)
        elif search_type == "elasticsearch" and self.elasticsearch_query_duration:
            self.elasticsearch_query_duration.record(duration, labels)

    def record_dms_operation(self, duration: float, adapter: str, operation: str, success: bool) -> None:
        """Record DMS operation metrics."""
        if not self.dms_request_duration:
            return
        
        labels = {
            "adapter": adapter,
            "operation": operation,
            "success": str(success),
        }
        
        self.dms_request_duration.record(duration, labels)

    def record_cache_operation(self, hit: bool) -> None:
        """Record cache hit/miss metrics."""
        if hit and self.cache_hits:
            self.cache_hits.add(1)
        elif not hit and self.cache_misses:
            self.cache_misses.add(1)

    def record_documents_indexed(self, count: int, namespace: str) -> None:
        """Record document indexing metrics."""
        if self.documents_indexed:
            self.documents_indexed.add(count, {"namespace": namespace})

    def record_model_inference(self, duration: float, model: str, success: bool) -> None:
        """Record AI model inference metrics."""
        if not self.model_inference_duration:
            return
        
        labels = {
            "model": model,
            "success": str(success),
        }
        
        self.model_inference_duration.record(duration, labels)

    def _get_count_bucket(self, count: int) -> str:
        """Get count bucket for metrics labeling."""
        if count == 0:
            return "0"
        elif count <= 5:
            return "1-5"
        elif count <= 10:
            return "6-10"
        elif count <= 20:
            return "11-20"
        elif count <= 50:
            return "21-50"
        else:
            return "50+"

    def create_span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """Create a new span for custom tracing."""
        if not self.tracer:
            return trace.NoOpSpan()
        
        span = self.tracer.start_span(name)
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, str(value))
        
        return span

    def shutdown(self) -> None:
        """Shutdown telemetry providers gracefully."""
        try:
            if self.tracer_provider:
                self.tracer_provider.shutdown()
            
            if self.meter_provider:
                self.meter_provider.shutdown()
            
            logger.info("Telemetry providers shutdown successfully")
            
        except Exception as e:
            logger.error(f"Error shutting down telemetry: {e}")


# Global telemetry instance
telemetry = TelemetryManager()