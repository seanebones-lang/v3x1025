#!/bin/bash
# Zero-downtime rolling update system

set -e

VERSION=${1:?"Version required: ./rolling-update.sh v1.2.3"}
NAMESPACE="dealership-rag"

echo "🔄 Starting rolling update to $VERSION"

# Pre-deployment checks
echo "🔍 Running pre-deployment validation..."
python3 health_check.py https://api.rag.yourdomain.com || exit 1

# Update container image
echo "📦 Updating container image..."
kubectl set image deployment/rag-api rag-api=dealership-rag:$VERSION -n $NAMESPACE

# Monitor rollout
echo "⏳ Monitoring rollout progress..."
kubectl rollout status deployment/rag-api -n $NAMESPACE --timeout=600s

# Post-deployment verification
echo "✅ Running post-deployment tests..."
sleep 30  # Allow for startup
python3 health_check.py https://api.rag.yourdomain.com || {
    echo "❌ Health check failed, initiating rollback..."
    kubectl rollout undo deployment/rag-api -n $NAMESPACE
    kubectl rollout status deployment/rag-api -n $NAMESPACE
    exit 1
}

# Load test
echo "🧪 Running load test..."
python3 load_test.py https://api.rag.yourdomain.com $API_KEY 5 60 || {
    echo "⚠️  Load test failed, consider rollback"
    exit 1
}

echo "✅ Rolling update completed successfully"

# Log deployment
cat << EOF >> deployment_history.log
$(date): Successfully deployed $VERSION
- Previous version: $(kubectl rollout history deployment/rag-api -n $NAMESPACE | tail -2 | head -1)
- New version: $VERSION
- Deployment time: $(date)
EOF