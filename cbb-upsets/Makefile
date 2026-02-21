# Makefile for local K3d (k3s) Kubernetes cluster management

.DEFAULT_GOAL := k8s-status

.PHONY: k8s-up k8s-down k8s-status ingress-up

k8s-up:
	@echo "[K3d] Creating local cluster..."
	k3d cluster create cbb-upsets-cluster --agents 2 --servers 1 --api-port 6550 -p "8080:80@loadbalancer" -p "8443:443@loadbalancer" || true
	@echo "Cluster created or already exists."

k8s-down:
	@echo "[K3d] Deleting local cluster..."
	k3d cluster delete cbb-upsets-cluster

k8s-status:
	@echo "[K3d] Current clusters:"
	k3d cluster list

ingress-up:
	@echo "[Kubernetes] Deploying NGINX ingress..."
	kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.1/deploy/static/provider/kind/deploy.yaml
