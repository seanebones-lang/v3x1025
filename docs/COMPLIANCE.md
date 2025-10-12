# Compliance & Audit Logging

## SOC 2 Compliance Readiness

### Audit Logging Requirements

#### Query Audit Log

Log all user queries for compliance:

```python
# In src/app.py
import json
from datetime import datetime

async def log_audit_event(event_type: str, data: dict):
    """Log audit events for compliance."""
    audit_entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "data": data,
        "environment": settings.environment
    }
    
    # Write to audit log file (rotate daily)
    with open(f"logs/audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl", "a") as f:
        f.write(json.dumps(audit_entry) + "\n")

# Add to query endpoint:
await log_audit_event("query", {
    "query_id": query_id,
    "query_text_hash": hashlib.sha256(request.query.encode()).hexdigest(),
    "user_id": user_id,  # If available
    "intent": result.get("intent"),
    "sources_accessed": [s["source"] for s in result.get("sources", [])],
    "processing_time_ms": query_time_ms
})
```

### Data Lineage Tracking

Track data flow for audit trails:

```python
# Add to document metadata
doc.metadata.update({
    "ingestion_timestamp": datetime.now().isoformat(),
    "ingestion_user": user_id,
    "source_system": "DMS",
    "data_classification": "internal",
    "retention_period_days": 365,
    "pii_present": False  # Set based on content analysis
})
```

### PII Anonymization

Implement before storing customer data:

```python
import re

def anonymize_pii(text: str) -> str:
    """Anonymize PII in text content."""
    # Email addresses
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', text)
    
    # Phone numbers (US format)
    text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[PHONE]', text)
    
    # SSN
    text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]', text)
    
    # Credit card numbers
    text = re.sub(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '[CARD]', text)
    
    # Driver's license (varies by state)
    text = re.sub(r'\b[A-Z]\d{7,8}\b', '[DL]', text)
    
    return text

# Apply in ingest pipeline:
doc.page_content = anonymize_pii(doc.page_content)
```

## GDPR Compliance

### Right to be Forgotten

Implement data deletion:

```python
# In src/app.py
@app.delete("/api/user/{user_id}/data")
async def delete_user_data(user_id: str):
    """Delete all user data for GDPR compliance."""
    # Delete from Pinecone
    await embedding_manager.index.delete(
        filter={"user_id": user_id},
        delete_all=True
    )
    
    # Delete from Redis cache
    cache_keys = await redis_client.keys(f"user:{user_id}:*")
    if cache_keys:
        await redis_client.delete(*cache_keys)
    
    # Log deletion
    await log_audit_event("gdpr_deletion", {
        "user_id": user_id,
        "timestamp": datetime.now().isoformat()
    })
    
    return {"status": "deleted", "user_id": user_id}
```

### Data Export (GDPR Article 20)

```python
@app.get("/api/user/{user_id}/export")
async def export_user_data(user_id: str):
    """Export user data in machine-readable format."""
    # Query all user data
    user_docs = await embedding_manager.query_vectors(
        query_text="",
        filter_dict={"user_id": user_id},
        top_k=1000
    )
    
    export_data = {
        "user_id": user_id,
        "export_date": datetime.now().isoformat(),
        "documents": [doc.metadata for doc in user_docs]
    }
    
    return export_data
```

## Access Control Audit

Track who accessed what:

```python
# Decorator for endpoints
def audit_access(resource_type: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user_id = kwargs.get("user_id", "anonymous")
            
            await log_audit_event("access", {
                "user_id": user_id,
                "resource_type": resource_type,
                "endpoint": func.__name__,
                "timestamp": datetime.now().isoformat()
            })
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Usage:
@app.get("/api/query")
@audit_access("query")
async def query(...):
    pass
```

## Data Retention Policy

Implement automated retention:

```python
# In Celery tasks
@celery_app.task
def cleanup_old_data():
    """Remove data past retention period."""
    cutoff_date = datetime.now() - timedelta(days=365)
    
    # Query old documents
    old_docs = embedding_manager.query_vectors(
        query_text="",
        filter_dict={"created_at__lt": cutoff_date.isoformat()},
        top_k=10000
    )
    
    # Delete in batches
    for i in range(0, len(old_docs), 100):
        batch = old_docs[i:i+100]
        ids = [doc["id"] for doc in batch]
        embedding_manager.index.delete(ids=ids)
    
    logger.info(f"Cleaned up {len(old_docs)} documents past retention")
```

## Compliance Checklist

- [x] Audit logging for all data access
- [x] PII anonymization before storage
- [x] Data deletion capabilities (GDPR)
- [x] Data export capabilities (GDPR Article 20)
- [x] Access control tracking
- [x] Retention policy implementation
- [ ] Encryption at rest (depends on infrastructure)
- [ ] Encryption in transit (HTTPS required)
- [ ] Regular security audits (quarterly recommended)
- [ ] Penetration testing (annual recommended)
- [ ] Third-party audit (for SOC 2 Type II)

## Compliance Reports

Generate compliance reports:

```python
def generate_compliance_report(start_date: str, end_date: str):
    """Generate compliance report for audit period."""
    # Parse audit logs
    # Aggregate metrics
    # Export to PDF/CSV
    
    report = {
        "period": f"{start_date} to {end_date}",
        "total_queries": 0,
        "data_access_events": 0,
        "deletion_requests": 0,
        "export_requests": 0,
        "security_incidents": 0
    }
    
    return report
```

## Reference Standards

- **SOC 2**: Service Organization Control 2
- **GDPR**: General Data Protection Regulation
- **CCPA**: California Consumer Privacy Act
- **HIPAA**: Not currently compliant (healthcare use requires additional controls)
- **PCI DSS**: Not handling payment card data

## Next Steps for Full Compliance

1. Enable HTTPS/TLS for all endpoints
2. Implement database encryption at rest
3. Set up automated backup and recovery
4. Configure log aggregation and retention
5. Establish incident response procedures
6. Conduct third-party security audit
7. Document data processing agreements
8. Train staff on compliance requirements

