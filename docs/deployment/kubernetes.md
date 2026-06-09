# Kubernetes Deployment Guide

This guide details steps for deploying the Repository Intelligence Agent to a Kubernetes cluster.

---

## Deployment Steps

### 1. Configure Secrets
First, replace the values in [secrets.yaml](file:///Users/atharvamendhulkar/Desktop/RuntimeOps/k8s/secrets.yaml) with base64-encoded production secrets (DB credentials and API keys).

Deploy secrets:
```bash
kubectl apply -f k8s/secrets.yaml
```

---

### 2. Configure Settings
Deploy configuration values:
```bash
kubectl apply -f k8s/configmap.yaml
```

---

### 3. Deploy the Service
Apply the Deployment and Service manifests to create pods and expose endpoints:
```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

---

### 4. Deploy Ingress
Apply the Ingress controller route configuration to expose endpoints publicly or internally:
```bash
kubectl apply -f k8s/ingress.yaml
```

---

## Verification

Check pod status:
```bash
kubectl get pods -l app=runtimeops-agent
```

Check logs:
```bash
kubectl logs -f deployment/runtimeops-agent
```

Test REST API health endpoint:
```bash
curl -f http://<ingress-host>/api/v1/bob/health
```
