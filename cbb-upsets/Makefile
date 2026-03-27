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

HELM_RELEASE := cbb-upsets
HELM_CHART := chart/cbb-upsets
HELM_VALUES := -f $(HELM_CHART)/values.yaml -f $(HELM_CHART)/values-local.yaml

K3D_CLUSTER_NAME := cbb-upsets-cluster
INGRESS_MANIFEST := https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.1/deploy/static/provider/kind/deploy.yaml

.PHONY: auto-loop-restart auto-loop-status auto-loop-stop auto-loop-up check format helm-lint helm-template infra-loop-status infra-loop-stop infra-loop-up ingress-up install k8s-down k8s-status k8s-up lint test typecheck

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

check: lint typecheck test helm-lint helm-template

helm-template:
	helm template $(HELM_RELEASE) $(HELM_CHART) $(HELM_VALUES)

helm-lint:
	helm lint $(HELM_CHART) $(HELM_VALUES)

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
	kubectl apply -f $(INGRESS_MANIFEST)

auto-loop-up:
	@mkdir -p .codex/local/auto-loop
	@if [ -f .codex/local/auto-loop/supervisor.pid ] && kill -0 "$$(cat .codex/local/auto-loop/supervisor.pid)" 2>/dev/null; then \
		echo "Autonomous loop supervisor already running."; \
	else \
		nohup $(PYTHON) scripts/run_autonomous_loops.py > .codex/local/auto-loop/supervisor.log 2>&1 & \
		echo $$! > .codex/local/auto-loop/launcher.pid; \
		sleep 1; \
		echo "Started autonomous loop supervisor. Use 'make auto-loop-status' for status."; \
	fi

auto-loop-status:
	$(PYTHON) scripts/run_autonomous_loops.py --status

auto-loop-stop:
	$(PYTHON) scripts/run_autonomous_loops.py --stop

auto-loop-restart:
	@mkdir -p .codex/local/auto-loop
	@$(PYTHON) scripts/run_autonomous_loops.py --stop >/dev/null 2>&1 || true
	@if [ -f .codex/local/auto-loop/supervisor.pid ]; then \
		for _ in $$(seq 1 30); do \
			pid="$$(cat .codex/local/auto-loop/supervisor.pid 2>/dev/null || true)"; \
			if [ -z "$$pid" ] || ! kill -0 "$$pid" 2>/dev/null; then \
				rm -f .codex/local/auto-loop/supervisor.pid; \
				break; \
			fi; \
			sleep 1; \
		done; \
		if [ -f .codex/local/auto-loop/supervisor.pid ]; then \
			echo "Timed out waiting for autonomous loop supervisor to stop."; \
			exit 1; \
		fi; \
	fi
	@rm -f .codex/local/auto-loop/launcher.pid
	@$(MAKE) --no-print-directory auto-loop-up

infra-loop-up:
	@mkdir -p .codex/local/auto-loop
	@if [ -f .codex/local/auto-loop/supervisor.pid ] && kill -0 "$$(cat .codex/local/auto-loop/supervisor.pid)" 2>/dev/null; then \
		echo "Infra loop supervisor already running."; \
	else \
		nohup $(PYTHON) scripts/run_infra_loops.py > .codex/local/auto-loop/supervisor.log 2>&1 & \
		echo $$! > .codex/local/auto-loop/launcher.pid; \
		sleep 1; \
		echo "Started infra loop supervisor. Use 'make infra-loop-status' for status."; \
	fi

infra-loop-status:
	$(PYTHON) scripts/run_infra_loops.py --status

infra-loop-stop:
	$(PYTHON) scripts/run_infra_loops.py --stop
