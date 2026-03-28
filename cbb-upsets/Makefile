SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

# Makefile for local K3d (k3s) Kubernetes cluster management

.DEFAULT_GOAL := k8s-status

VENV := .venv
VENV_BIN := $(VENV)/bin
PYTHON := $(VENV_BIN)/python
PIP := $(PYTHON) -m pip
PYTEST := $(VENV_BIN)/pytest
RUFF := $(VENV_BIN)/ruff
MYPY := $(VENV_BIN)/mypy
HELM := helm
KUBECTL := kubectl

HELM_RELEASE := cbb-upsets
HELM_CHART := chart/cbb-upsets
HELM_VALUES := -f $(HELM_CHART)/values.yaml -f $(HELM_CHART)/values-local.yaml
K8S_NAMESPACE := default
POSTGRES_SERVICE := $(HELM_RELEASE)-postgresql
POSTGRES_LOCAL_PORT := 5432
POSTGRES_REMOTE_PORT := 5432

K3D_CLUSTER_NAME := cbb-upsets-cluster
INGRESS_MANIFEST := https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.1/deploy/static/provider/kind/deploy.yaml

.PHONY: check db-port-forward format helm-check helm-lint helm-template helm-up ingress-up install k8s-down k8s-status k8s-up lint test typecheck

install:
	python3 -m venv $(VENV)
	$(PIP) install -e ".[dev]"

test:
	$(PYTEST)

lint:
	$(RUFF) check src tests scripts

format:
	$(RUFF) check --select I --fix src tests scripts
	$(RUFF) format src tests scripts

typecheck:
	$(MYPY)

check: lint typecheck test helm-check

helm-check: helm-lint helm-template

helm-template:
	$(HELM) template $(HELM_RELEASE) $(HELM_CHART) $(HELM_VALUES)

helm-lint:
	$(HELM) lint $(HELM_CHART) $(HELM_VALUES)

helm-up:
	$(HELM) upgrade --install $(HELM_RELEASE) $(HELM_CHART) $(HELM_VALUES)

k8s-up:
	@echo "[K3d] Creating local cluster..."
	k3d cluster create $(K3D_CLUSTER_NAME) \
		--agents 2 \
		--servers 1 \
		--api-port 6550 \
		-p "8080:80@loadbalancer" \
		-p "8443:443@loadbalancer" || true
	@echo "Cluster created or already exists."

k8s-down:
	@echo "[K3d] Deleting local cluster..."
	k3d cluster delete $(K3D_CLUSTER_NAME)

k8s-status:
	@echo "[K3d] Current clusters:"
	k3d cluster list

ingress-up:
	@echo "[Kubernetes] Deploying NGINX ingress..."
	$(KUBECTL) apply -f $(INGRESS_MANIFEST)

db-port-forward:
	$(KUBECTL) port-forward svc/$(POSTGRES_SERVICE) \
		$(POSTGRES_LOCAL_PORT):$(POSTGRES_REMOTE_PORT) \
		--address 127.0.0.1 \
		-n $(K8S_NAMESPACE)
