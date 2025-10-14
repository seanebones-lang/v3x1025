#!/bin/bash
# Emergency rollback system

NAMESPACE="dealership-rag"

echo "🚨 INITIATING EMERGENCY ROLLBACK"

# Get rollout history
echo "📜 Deployment history:"
kubectl rollout history deployment/rag-api -n $NAMESPACE

# Rollback to previous version
echo "⏪ Rolling back to previous version..."
kubectl rollout undo deployment/rag-api -n $NAMESPACE

# Wait for rollback completion
echo "⏳ Waiting for rollback completion..."
kubectl rollout status deployment/rag-api -n $NAMESPACE --timeout=300s

# Verify system health
echo "🏥 Verifying system health..."
sleep 30
python3 health_check.py https://api.rag.yourdomain.com || {
    echo "❌ Rollback failed - system still unhealthy"
    exit 1
}

echo "✅ Emergency rollback completed successfully"

# Log rollback
echo "$(date): Emergency rollback completed" >> deployment_history.log