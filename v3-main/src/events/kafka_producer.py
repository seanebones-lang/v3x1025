"""
Event-driven data ingestion system with Apache Kafka.
Handles real-time document updates, DMS synchronization, and system events.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

import aiokafka
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from pydantic import BaseModel

from src.config import get_config

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Types of events in the system."""
    DOCUMENT_INGESTED = "document.ingested"
    DOCUMENT_UPDATED = "document.updated"
    DOCUMENT_DELETED = "document.deleted"
    QUERY_EXECUTED = "query.executed"
    DMS_SYNC_STARTED = "dms.sync.started"
    DMS_SYNC_COMPLETED = "dms.sync.completed"
    TENANT_CREATED = "tenant.created"
    API_KEY_ROTATED = "apikey.rotated"
    SYSTEM_ALERT = "system.alert"
    AUDIT_LOG = "audit.log"


class Event(BaseModel):
    """Base event model."""
    event_id: str = None
    event_type: EventType
    timestamp: datetime = None
    tenant_id: str
    source_service: str
    correlation_id: Optional[str] = None
    payload: Dict[str, Any]
    metadata: Dict[str, Any] = {}

    def __init__(self, **data):
        if not data.get('event_id'):
            data['event_id'] = str(uuid4())
        if not data.get('timestamp'):
            data['timestamp'] = datetime.now()
        super().__init__(**data)


class DocumentEvent(Event):
    """Document-specific event."""
    def __init__(self, event_type: EventType, tenant_id: str, document_id: str, **kwargs):
        payload = {
            'document_id': document_id,
            **kwargs.get('payload', {})
        }
        super().__init__(
            event_type=event_type,
            tenant_id=tenant_id,
            payload=payload,
            **kwargs
        )


class QueryEvent(Event):
    """Query execution event."""
    def __init__(self, tenant_id: str, query: str, intent: str, response_time_ms: float, **kwargs):
        payload = {
            'query': query,
            'intent': intent,
            'response_time_ms': response_time_ms,
            **kwargs.get('payload', {})
        }
        super().__init__(
            event_type=EventType.QUERY_EXECUTED,
            tenant_id=tenant_id,
            payload=payload,
            **kwargs
        )


class EventProducer:
    """High-performance Kafka event producer with batching and compression."""
    
    def __init__(self):
        self.config = get_config()
        self.producer: Optional[AIOKafkaProducer] = None
        self.kafka_servers = [
            "kafka-0.kafka.dealership-rag.svc.cluster.local:9092",
            "kafka-1.kafka.dealership-rag.svc.cluster.local:9092",
            "kafka-2.kafka.dealership-rag.svc.cluster.local:9092",
        ]
        
        # Topic configuration
        self.topics = {
            'documents': 'rag-documents',
            'queries': 'rag-queries', 
            'dms': 'rag-dms-sync',
            'audit': 'rag-audit',
            'system': 'rag-system',
        }
        
        # Performance metrics
        self.events_produced = 0
        self.production_errors = 0

    async def initialize(self) -> None:
        """Initialize Kafka producer with optimal settings."""
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.kafka_servers,
                value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8'),
                compression_type="snappy",  # Fast compression
                batch_size=16384,  # 16KB batches
                linger_ms=10,  # 10ms batching window
                max_request_size=1048576,  # 1MB max message size
                retries=5,
                retry_backoff_ms=100,
                request_timeout_ms=30000,
                acks='all',  # Wait for all replicas
                enable_idempotence=True,  # Prevent duplicates
                max_in_flight_requests_per_connection=1,  # Preserve order
            )
            
            await self.producer.start()
            logger.info("Kafka producer initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            raise

    async def produce_event(
        self,
        event: Event,
        topic_key: str = 'system',
        partition_key: Optional[str] = None
    ) -> None:
        """Produce event to Kafka topic."""
        if not self.producer:
            logger.warning("Producer not initialized, dropping event")
            return
        
        try:
            topic = self.topics.get(topic_key, self.topics['system'])
            
            # Use tenant_id as partition key for tenant isolation
            key = (partition_key or event.tenant_id).encode('utf-8')
            
            # Convert event to dict for serialization
            event_data = event.model_dump()
            
            # Add routing metadata
            event_data['_routing'] = {
                'topic': topic,
                'partition_key': partition_key or event.tenant_id,
                'producer_timestamp': time.time(),
            }
            
            await self.producer.send_and_wait(
                topic,
                value=event_data,
                key=key
            )
            
            self.events_produced += 1
            
            if self.events_produced % 1000 == 0:
                logger.info(f"Produced {self.events_produced} events to Kafka")
                
        except Exception as e:
            self.production_errors += 1
            logger.error(f"Failed to produce event {event.event_id}: {e}")
            
            # Optionally store failed events for retry
            await self._store_failed_event(event, str(e))

    async def produce_document_event(
        self,
        event_type: EventType,
        tenant_id: str,
        document_id: str,
        **kwargs
    ) -> None:
        """Produce document-related event."""
        event = DocumentEvent(
            event_type=event_type,
            tenant_id=tenant_id,
            document_id=document_id,
            source_service="rag-api",
            **kwargs
        )
        
        await self.produce_event(event, topic_key='documents')

    async def produce_query_event(
        self,
        tenant_id: str,
        query: str,
        intent: str,
        response_time_ms: float,
        **kwargs
    ) -> None:
        """Produce query execution event."""
        event = QueryEvent(
            tenant_id=tenant_id,
            query=query,
            intent=intent,
            response_time_ms=response_time_ms,
            source_service="rag-api",
            **kwargs
        )
        
        await self.produce_event(event, topic_key='queries')

    async def produce_audit_event(
        self,
        tenant_id: str,
        action: str,
        resource: str,
        user_id: str,
        **kwargs
    ) -> None:
        """Produce audit trail event."""
        event = Event(
            event_type=EventType.AUDIT_LOG,
            tenant_id=tenant_id,
            source_service="rag-api",
            payload={
                'action': action,
                'resource': resource,
                'user_id': user_id,
                **kwargs
            }
        )
        
        await self.produce_event(event, topic_key='audit')

    async def close(self) -> None:
        """Close producer and cleanup resources."""
        if self.producer:
            await self.producer.stop()
            logger.info(f"Kafka producer closed. Stats: {self.events_produced} produced, {self.production_errors} errors")

    async def _store_failed_event(self, event: Event, error: str) -> None:
        """Store failed event for retry processing."""
        # Implementation would store in dead letter queue
        logger.warning(f"Storing failed event {event.event_id} for retry: {error}")


class EventConsumer:
    """High-performance Kafka event consumer with parallel processing."""
    
    def __init__(self, consumer_group: str, topics: List[str]):
        self.config = get_config()
        self.consumer_group = consumer_group
        self.topics = topics
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.kafka_servers = [
            "kafka-0.kafka.dealership-rag.svc.cluster.local:9092",
            "kafka-1.kafka.dealership-rag.svc.cluster.local:9092", 
            "kafka-2.kafka.dealership-rag.svc.cluster.local:9092",
        ]
        
        # Processing stats
        self.events_processed = 0
        self.processing_errors = 0
        self.processing_tasks: Set[asyncio.Task] = set()

    async def initialize(self) -> None:
        """Initialize Kafka consumer."""
        try:
            self.consumer = AIOKafkaConsumer(
                *self.topics,
                bootstrap_servers=self.kafka_servers,
                group_id=self.consumer_group,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='earliest',
                enable_auto_commit=False,  # Manual commit for reliability
                max_poll_records=500,  # Batch processing
                fetch_max_bytes=52428800,  # 50MB max fetch
                consumer_timeout_ms=1000,
            )
            
            await self.consumer.start()
            logger.info(f"Kafka consumer initialized for group {self.consumer_group}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Kafka consumer: {e}")
            raise

    async def start_consuming(self, processor_func) -> None:
        """Start consuming events with parallel processing."""
        if not self.consumer:
            await self.initialize()
        
        logger.info(f"Starting consumer for topics: {self.topics}")
        
        try:
            async for message in self.consumer:
                # Create processing task
                task = asyncio.create_task(
                    self._process_message(message, processor_func)
                )
                self.processing_tasks.add(task)
                
                # Clean up completed tasks
                self.processing_tasks = {
                    task for task in self.processing_tasks 
                    if not task.done()
                }
                
                # Limit concurrent processing
                if len(self.processing_tasks) >= 100:
                    done, pending = await asyncio.wait(
                        self.processing_tasks,
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    self.processing_tasks = pending
                
        except Exception as e:
            logger.error(f"Consumer error: {e}")
            raise
        finally:
            # Wait for all processing to complete
            if self.processing_tasks:
                await asyncio.wait(self.processing_tasks)

    async def _process_message(self, message, processor_func) -> None:
        """Process individual message with error handling."""
        try:
            event_data = message.value
            event = Event(**event_data)
            
            # Process the event
            await processor_func(event)
            
            # Commit offset after successful processing
            await self.consumer.commit({
                message.topic_partition: message.offset + 1
            })
            
            self.events_processed += 1
            
            if self.events_processed % 1000 == 0:
                logger.info(f"Processed {self.events_processed} events")
            
        except Exception as e:
            self.processing_errors += 1
            logger.error(f"Failed to process message: {e}")
            
            # Optionally send to dead letter queue
            await self._handle_processing_error(message, e)

    async def _handle_processing_error(self, message, error: Exception) -> None:
        """Handle processing errors with retry logic."""
        # Implementation would include:
        # 1. Retry logic with exponential backoff
        # 2. Dead letter queue for persistent failures
        # 3. Error alerting
        logger.warning(f"Processing error for message at offset {message.offset}: {error}")

    async def close(self) -> None:
        """Close consumer and cleanup."""
        if self.processing_tasks:
            await asyncio.wait(self.processing_tasks)
        
        if self.consumer:
            await self.consumer.stop()
            logger.info(f"Consumer closed. Stats: {self.events_processed} processed, {self.processing_errors} errors")


# Global producer instance
event_producer = EventProducer()


async def initialize_event_system() -> None:
    """Initialize the event system."""
    await event_producer.initialize()


async def cleanup_event_system() -> None:
    """Cleanup event system resources."""
    await event_producer.close()