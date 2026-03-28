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
DOCKER := docker

HELM_RELEASE := cbb-upsets
HELM_CHART := chart/cbb-upsets
HELM_CHART_DEPS_DIR := $(HELM_CHART)/charts
HELM_VALUES := -f $(HELM_CHART)/values.yaml -f $(HELM_CHART)/values-local.yaml
K8S_NAMESPACE := default
POSTGRES_SERVICE := $(HELM_RELEASE)-postgresql
POSTGRES_LOCAL_PORT := 5432
POSTGRES_REMOTE_PORT := 5432

K3D_CLUSTER_NAME := cbb-upsets-cluster
INGRESS_MANIFEST := https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.1/deploy/static/provider/kind/deploy.yaml
CLI_IMAGE_NAME ?= cbb-upsets-cli
CLI_IMAGE_TAG ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)
CLI_IMAGE := $(CLI_IMAGE_NAME):$(CLI_IMAGE_TAG)

.PHONY: check cli-image-build cli-image-load db-port-forward format helm-bootstrap helm-check helm-deps helm-lint helm-status helm-template helm-template-check helm-up ingress-up install k8s-down k8s-status k8s-up lint test typecheck

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

cli-image-build:
	$(DOCKER) build -t $(CLI_IMAGE) .

cli-image-load:
	k3d image import $(CLI_IMAGE) -c $(K3D_CLUSTER_NAME)

helm-bootstrap:
	@if [ -d "$(HELM_CHART_DEPS_DIR)" ] && find $(HELM_CHART_DEPS_DIR) -maxdepth 1 -name '*.tgz' -print -quit | grep -q .; then \
		echo "[Helm] Chart dependencies already present." >&2; \
	else \
		$(HELM) dependency build --skip-refresh $(HELM_CHART) >&2; \
	fi

helm-deps:
	$(HELM) dependency build --skip-refresh $(HELM_CHART)

helm-check: helm-bootstrap helm-lint helm-template-check

helm-template-check: helm-bootstrap
	@render_path="$$(mktemp -t $(HELM_RELEASE)-template)"; \
	$(HELM) template $(HELM_RELEASE) $(HELM_CHART) $(HELM_VALUES) > "$$render_path"; \
	line_count="$$(wc -l < "$$render_path" | tr -d ' ')"; \
	echo "[Helm] Rendered manifest -> $$render_path ($$line_count lines)"

helm-template: helm-bootstrap
	@$(HELM) template $(HELM_RELEASE) $(HELM_CHART) $(HELM_VALUES)

helm-lint:
	$(HELM) lint $(HELM_CHART) $(HELM_VALUES)

helm-status:
	$(HELM) status $(HELM_RELEASE) -n $(K8S_NAMESPACE)

helm-up: helm-check
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
