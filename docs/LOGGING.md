# Logging & Observability Guide

## Structured Logging with Structlog

For production deployments, use structured logging for better observability.

### Setup

```python
# In src/__init__.py or main app initialization
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()
```

### Usage in Code

Replace print statements with structured logs:

```python
# Instead of:
print(f"DMS tool call - Intent: {intent}, Query: {query}")

# Use:
logger.info(
    "dms_tool_call_initiated",
    intent=intent,
    query=query[:50],
    timestamp=datetime.now().isoformat()
)
```

### Log Levels

- **DEBUG**: Detailed diagnostic information
- **INFO**: General informational messages (DMS calls, queries)
- **WARNING**: Warning messages (fallbacks, retries)
- **ERROR**: Error messages (failures, exceptions)
- **CRITICAL**: Critical failures requiring immediate attention

### Production Logging

```python
# Example structured log in src/agent.py
logger.info(
    "query_processed",
    query_id=query_id,
    intent=intent.intent,
    intent_confidence=intent.confidence,
    dms_call_made=bool(dms_result),
    retrieval_docs=len(context_docs),
    processing_time_ms=processing_time,
    user_id=user_id,  # If available
)
```

### Integration with Observability Platforms

#### DataDog
```python
from ddtrace import tracer

@tracer.wrap(service="dealership-rag", resource="query")
async def process_query(query: str):
    # Your code
    pass
```

#### New Relic
```python
import newrelic.agent

@newrelic.agent.background_task()
async def process_document(file_path: str):
    # Your code
    pass
```

#### OpenTelemetry (Generic)
```python
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# In app.py lifespan
FastAPIInstrumentor.instrument_app(app)

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("query_processing"):
    # Your code
    pass
```

### Log Aggregation

#### ELK Stack
Send logs to Elasticsearch via Logstash or Filebeat:
```yaml
# filebeat.yml
filebeat.inputs:
  - type: log
    paths:
      - /app/logs/*.log
    json.keys_under_root: true
output.elasticsearch:
  hosts: ["elasticsearch:9200"]
```

#### CloudWatch (AWS)
```python
import watchtower

logging.basicConfig(level=logging.INFO)
logger.addHandler(watchtower.CloudWatchLogHandler(log_group="/dealership-rag"))
```

#### Google Cloud Logging
```python
from google.cloud import logging as cloud_logging

client = cloud_logging.Client()
client.setup_logging()
```

### Metrics to Log

**Query Metrics:**
- Query text (sanitized)
- Intent classification
- Retrieval time
- Generation time
- Total processing time
- Number of sources used
- Cache hit/miss

**DMS Metrics:**
- Tool called
- Response time
- Success/failure
- Number of records returned
- Filters applied

**Error Metrics:**
- Error type
- Error message
- Stack trace
- Request context
- User ID (if available)

### Example Production Logger

```python
# src/utils/logger.py
import structlog
import logging
from src.config import settings

def configure_logging():
    """Configure structured logging for production."""
    
    if settings.is_production:
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ]
    else:
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
        ]
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    return structlog.get_logger()

# Usage:
# from src.utils.logger import configure_logging
# logger = configure_logging()
```

### Performance Monitoring

Track these metrics in production:

```python
import time

start = time.perf_counter()
# ... operation ...
duration_ms = (time.perf_counter() - start) * 1000

logger.info(
    "operation_complete",
    operation="embedding_generation",
    duration_ms=duration_ms,
    num_docs=len(documents),
    avg_ms_per_doc=duration_ms / len(documents)
)
```

### Alerting Rules

Configure alerts in your monitoring platform:

- **High Latency**: p95 > 3s for 5 minutes
- **High Error Rate**: >2% errors for 5 minutes
- **Low Cache Hit**: <50% for 10 minutes
- **DMS Failures**: >5 failures in 10 minutes
- **Memory Usage**: >90% for 5 minutes
- **Queue Backlog**: >1000 tasks in Celery queue

### Best Practices

1. **Never log sensitive data** (customer PII, API keys)
2. **Use log levels appropriately** (not everything is ERROR)
3. **Add context** (request IDs, user IDs, session IDs)
4. **Structured over unstructured** (JSON logs are searchable)
5. **Sample in high volume** (don't log every request at scale)
6. **Rotate logs** (use logrotate or cloud service limits)
7. **Monitor log volume** (high volume = potential issue)

### Log Sampling

For high-traffic endpoints, sample logs:

```python
import random

if random.random() < 0.1:  # Log 10% of requests
    logger.info("query_sample", ...)
```

### Reference

- Structlog docs: https://www.structlog.org/
- OpenTelemetry: https://opentelemetry.io/
- Python logging: https://docs.python.org/3/library/logging.html

