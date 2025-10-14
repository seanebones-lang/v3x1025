#!/bin/bash
# Automated domain and SSL setup

DOMAIN=${1:-"rag.yourdomain.com"}
EMAIL=${2:-"admin@yourdomain.com"}

echo "🌐 Setting up domain: $DOMAIN"

# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Wait for cert-manager to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=cert-manager -n cert-manager --timeout=300s

# Create cluster issuer
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: $EMAIL
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF

echo "✅ SSL certificate management configured"
echo "📋 Next steps:"
echo "   1. Point $DOMAIN to your load balancer IP"
echo "   2. Wait 5-10 minutes for DNS propagation" 
echo "   3. SSL certificate will be automatically issued"