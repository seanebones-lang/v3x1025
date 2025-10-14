# Kubernetes Deployment

This directory contains Kubernetes manifests and Helm charts for deploying the Dealership RAG system at scale.

## Quick Start with Helm

### Prerequisites
- Kubernetes cluster (1.19+)
- Helm 3.x installed
- kubectl configured

### Installation

```bash
# 1. Create namespace
kubectl create namespace dealership-rag

# 2. Create secrets
kubectl create secret generic dealership-rag-secrets \
  --from-literal=anthropic-api-key=YOUR_KEY \
  --from-literal=voyage-api-key=YOUR_KEY \
  --from-literal=cohere-api-key=YOUR_KEY \
  --from-literal=pinecone-api-key=YOUR_KEY \
  -n dealership-rag

# 3. Install with Helm
helm install dealership-rag ./helm-chart \
  --namespace dealership-rag \
  --values ./helm-chart/values.yaml

# 4. Verify deployment
kubectl get pods -n dealership-rag
kubectl get svc -n dealership-rag
```

### Configuration

Edit `helm-chart/values.yaml` to customize:
- **Autoscaling**: Min/max replicas, CPU/memory thresholds
- **Resources**: CPU/memory limits and requests
- **Ingress**: Domain name, TLS certificates
- **Redis**: Persistence, memory limits
- **Celery**: Worker count, resource allocation

### Scaling

```bash
# Manual scaling
kubectl scale deployment dealership-rag --replicas=5 -n dealership-rag

# Autoscaling is enabled by default (2-10 replicas)
kubectl get hpa -n dealership-rag

# Watch autoscaling events
kubectl describe hpa dealership-rag -n dealership-rag
```

### Monitoring

```bash
# Check pod status
kubectl get pods -n dealership-rag -w

# View logs
kubectl logs -f deployment/dealership-rag -n dealership-rag

# Check health
kubectl exec -it deployment/dealership-rag -n dealership-rag -- curl localhost:8000/api/health

# Metrics (if Prometheus installed)
kubectl port-forward svc/prometheus 9090:9090 -n monitoring
```

### Upgrading

```bash
# Update image tag
helm upgrade dealership-rag ./helm-chart \
  --namespace dealership-rag \
  --set image.tag=v1.1.0 \
  --reuse-values

# Rollback if needed
helm rollback dealership-rag -n dealership-rag
```

### Uninstall

```bash
helm uninstall dealership-rag -n dealership-rag
kubectl delete namespace dealership-rag
```

## Architecture

The Helm chart deploys:
- **API Deployment**: 2-10 replicas (autoscaling)
- **Redis StatefulSet**: Caching and Celery broker
- **Celery Worker Deployment**: Background tasks
- **Celery Beat Deployment**: Scheduled jobs
- **Service**: ClusterIP for internal communication
- **Ingress**: External access with TLS
- **HPA**: Horizontal Pod Autoscaler
- **Secrets**: API keys and sensitive data

## Production Recommendations

1. **Resource Limits**: Set based on load testing
2. **Persistent Storage**: Use StorageClass with backups for Redis
3. **Secrets Management**: Use external secrets (AWS Secrets Manager, HashiCorp Vault)
4. **Monitoring**: Install Prometheus + Grafana for metrics
5. **Logging**: Use Fluentd/Fluent Bit for centralized logging
6. **TLS**: Use cert-manager for automatic certificate management
7. **Network Policies**: Restrict pod-to-pod communication
8. **Pod Disruption Budgets**: Ensure availability during updates

## Cost Optimization

- Use **node affinity** to run on cheaper instance types
- Enable **cluster autoscaler** to scale nodes
- Use **spot instances** for non-critical workloads
- Set **resource requests** accurately to improve bin packing
- Monitor **idle resources** and adjust limits

## Troubleshooting

```bash
# Pod not starting
kubectl describe pod POD_NAME -n dealership-rag

# Check events
kubectl get events -n dealership-rag --sort-by='.lastTimestamp'

# Resource issues
kubectl top pods -n dealership-rag
kubectl top nodes

# Network debugging
kubectl run debug --image=nicolaka/netshoot -it --rm -n dealership-rag
```

## Support

For issues or questions:
- Check logs: `kubectl logs -f deployment/dealership-rag -n dealership-rag`
- Review events: `kubectl get events -n dealership-rag`
- GitHub Issues: https://github.com/seanebones-lang/AutoRAG/issues

