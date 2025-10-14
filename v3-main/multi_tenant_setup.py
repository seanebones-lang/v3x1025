#!/usr/bin/env python3
"""
Multi-tenant setup script for dealership locations.
"""
import yaml
import os
from typing import Dict, List


def generate_dealership_config(dealership_id: str, dealership_name: str, dms_type: str) -> Dict:
    """Generate configuration for a specific dealership."""
    
    return {
        "dealership": {
            "id": dealership_id,
            "name": dealership_name,
            "namespace": f"dealership-{dealership_id}",
        },
        "dms": {
            "adapter": dms_type,
            "api_key_secret": f"{dealership_id}-dms-key",
            "api_url": {
                "cdk": "https://api.cdkglobal.com/v1",
                "reynolds": "https://api.reyrey.com/v1"
            }.get(dms_type, ""),
        },
        "resources": {
            "replicas": 2,
            "cpu_request": "500m",
            "cpu_limit": "1000m", 
            "memory_request": "1Gi",
            "memory_limit": "2Gi"
        },
        "ingress": {
            "host": f"{dealership_id}.rag.yourdomain.com",
            "tls_secret": f"{dealership_id}-tls"
        }
    }


def create_k8s_manifests(config: Dict) -> List[str]:
    """Create Kubernetes manifests for a dealership."""
    
    dealership_id = config["dealership"]["id"]
    namespace = config["dealership"]["namespace"]
    
    manifests = []
    
    # Namespace
    namespace_yaml = f"""
apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
  labels:
    dealership-id: {dealership_id}
    app.kubernetes.io/name: dealership-rag
"""
    manifests.append(("namespace.yaml", namespace_yaml))
    
    # ConfigMap
    configmap_yaml = f"""
apiVersion: v1
kind: ConfigMap
metadata:
  name: rag-config
  namespace: {namespace}
data:
  DEALERSHIP_ID: "{dealership_id}"
  DMS_ADAPTER: "{config['dms']['adapter']}"
  ENVIRONMENT: "production"
  # ... other config values
"""
    manifests.append(("configmap.yaml", configmap_yaml))
    
    # Deployment
    deployment_yaml = f"""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rag-api
  namespace: {namespace}
spec:
  replicas: {config['resources']['replicas']}
  selector:
    matchLabels:
      app: rag-api
      dealership: {dealership_id}
  template:
    metadata:
      labels:
        app: rag-api
        dealership: {dealership_id}
    spec:
      containers:
      - name: rag-api
        image: dealership-rag:latest
        resources:
          requests:
            cpu: {config['resources']['cpu_request']}
            memory: {config['resources']['memory_request']}
          limits:
            cpu: {config['resources']['cpu_limit']}
            memory: {config['resources']['memory_limit']}
        # ... rest of container spec
"""
    manifests.append(("deployment.yaml", deployment_yaml))
    
    return manifests


def setup_dealership(dealership_id: str, dealership_name: str, dms_type: str):
    """Set up RAG system for a specific dealership."""
    
    print(f"🏢 Setting up RAG system for {dealership_name} (ID: {dealership_id})")
    
    # Generate configuration
    config = generate_dealership_config(dealership_id, dealership_name, dms_type)
    
    # Create output directory
    output_dir = f"deployments/{dealership_id}"
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate manifests
    manifests = create_k8s_manifests(config)
    
    # Write files
    for filename, content in manifests:
        with open(f"{output_dir}/{filename}", "w") as f:
            f.write(content)
    
    # Write configuration
    with open(f"{output_dir}/config.yaml", "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    
    # Generate deployment script
    deploy_script = f"""#!/bin/bash
echo "Deploying RAG system for {dealership_name}..."
kubectl apply -f {output_dir}/namespace.yaml
kubectl apply -f {output_dir}/configmap.yaml  
kubectl apply -f {output_dir}/deployment.yaml
kubectl apply -f {output_dir}/service.yaml
kubectl apply -f {output_dir}/ingress.yaml
echo "✅ Deployment complete for {dealership_name}"
echo "🔗 URL: https://{config['ingress']['host']}"
"""
    
    with open(f"{output_dir}/deploy.sh", "w") as f:
        f.write(deploy_script)
    os.chmod(f"{output_dir}/deploy.sh", 0o755)
    
    print(f"✅ Configuration generated in {output_dir}/")
    print(f"🚀 Run: ./{output_dir}/deploy.sh to deploy")


if __name__ == "__main__":
    # Example usage
    dealerships = [
        ("downtown-ford", "Downtown Ford", "cdk"),
        ("suburban-honda", "Suburban Honda", "reynolds"),
        ("premium-bmw", "Premium BMW", "cdk"),
    ]
    
    for dealership_id, name, dms in dealerships:
        setup_dealership(dealership_id, name, dms)
    
    print("🎉 All dealership configurations generated!")