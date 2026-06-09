#!/usr/bin/env bash
# ==============================================================================
# Local Kubernetes Deployment Verification Script
# ==============================================================================

set -eo pipefail

NAMESPACE="runtimeops"
DEPLOYMENT_NAME="runtimeops-agent"
SERVICE_NAME="runtimeops-agent"

echo "=== [1/5] Creating Namespace '$NAMESPACE' ==="
kubectl create namespace "$NAMESPACE" || echo "Namespace already exists"

echo "=== [2/5] Deploying Manifests ==="
# Apply secrets and configmaps first
kubectl apply -f k8s/secrets.yaml -n "$NAMESPACE"
kubectl apply -f k8s/configmap.yaml -n "$NAMESPACE"

# Apply deployment and services
kubectl apply -f k8s/deployment.yaml -n "$NAMESPACE"
kubectl apply -f k8s/service.yaml -n "$NAMESPACE"
kubectl apply -f k8s/ingress.yaml -n "$NAMESPACE"

echo "=== [3/5] Waiting for Deployment Availability ==="
kubectl rollout status deployment/"$DEPLOYMENT_NAME" -n "$NAMESPACE" --timeout=150s

echo "=== [4/5] Inspecting Resource Status ==="
kubectl get all -n "$NAMESPACE"

echo "=== [5/5] Performing Health Check & Probe Verification ==="
# Find one of the running pods
POD_NAME=$(kubectl get pods -n "$NAMESPACE" -l app=runtimeops-agent -o jsonpath='{.items[0].metadata.name}')
echo "Found running agent pod: $POD_NAME"

echo "Running readiness probe on pod:"
kubectl exec -it "$POD_NAME" -n "$NAMESPACE" -- curl -f http://localhost:8000/readiness

echo "Running health check probe on pod:"
kubectl exec -it "$POD_NAME" -n "$NAMESPACE" -- curl -f http://localhost:8000/health

echo "=== Local Kubernetes Verification Succeeded ==="
