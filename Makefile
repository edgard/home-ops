# ---- Makefile for ArgoCD-managed Kind homelab ------------------------------
.DEFAULT_GOAL := help

REPO_ROOT      := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
PYTHON         ?= python3
CLUSTER_DIR    := $(REPO_ROOT)bootstrap
CLUSTER_CONFIG_DIR := $(CLUSTER_DIR)/config
BOOTSTRAP      := $(PYTHON) $(REPO_ROOT)bootstrap/scripts/bootstrap.py
KIND           ?= kind
KIND_CONFIG    ?= $(CLUSTER_CONFIG_DIR)/cluster-config.yaml
KIND_CONFIG_NAME := $(shell awk '/^name:[[:space:]]*/ {sub(/^name:[[:space:]]*/, ""); print; exit}' "$(KIND_CONFIG)" 2>/dev/null)
CLUSTER_NAME   := $(if $(KIND_CONFIG_NAME),$(KIND_CONFIG_NAME),homelab)
KUBECTL        ?= kubectl
SOPS           ?= sops
SOPS_AGE_KEY_FILE ?= $(REPO_ROOT).sops.agekey
CLUSTER_SECRETS_SOPS := $(CLUSTER_CONFIG_DIR)/cluster-secrets.sops.yaml
CLUSTER_SECRETS_TEMPLATE := $(CLUSTER_CONFIG_DIR)/cluster-secrets.template.yaml
AGE_KEYGEN     ?= age-keygen
PRETTIER       ?= prettier
YAMLFMT        ?= yamlfmt
YAMLLINT       ?= yamllint
ARGOCD_SELECTOR ?=
.PHONY: help bootstrap bootstrap-delete bootstrap-recreate kind-create kind-delete kind-recreate kind-status \
    secrets-edit secrets-apply secrets-create-key argo-sync

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "}; /^[a-zA-Z0-9_\-]+:.*?## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo "\nPaths:"
	@echo "  CLUSTER_DIR=$(CLUSTER_DIR)"
	@echo "  CLUSTER_NAME=$(CLUSTER_NAME)  KIND_CONFIG=$(KIND_CONFIG)"

bootstrap: ## Provision Kind cluster on remote Docker host and install Argo CD
	$(BOOTSTRAP)

bootstrap-delete: ## Delete the Kind cluster via the bootstrap script
	$(BOOTSTRAP) --delete

bootstrap-recreate: ## Delete and rebuild the Kind cluster via the bootstrap script
	-$(MAKE) bootstrap-delete
	$(MAKE) bootstrap

kind-create: ## Create a local Kind cluster using the repo configuration
	$(KIND) create cluster --config "$(KIND_CONFIG)"

kind-delete: ## Delete the local Kind cluster
	$(KIND) delete cluster --name "$(CLUSTER_NAME)"

kind-recreate: ## Recreate the Kind cluster from scratch
	-$(KIND) delete cluster --name "$(CLUSTER_NAME)"
	$(MAKE) kind-create

kind-status: ## Show Kind nodes and their status
	$(KUBECTL) get nodes -o wide

secrets-edit: ## Create or edit the encrypted cluster secrets with SOPS
	@if [ ! -f "$(CLUSTER_SECRETS_SOPS)" ]; then \
		if [ ! -f "$(CLUSTER_SECRETS_TEMPLATE)" ]; then \
			echo "Template $(CLUSTER_SECRETS_TEMPLATE) not found"; \
			exit 1; \
		fi; \
		cp "$(CLUSTER_SECRETS_TEMPLATE)" "$(CLUSTER_SECRETS_SOPS)"; \
		echo "Created $(CLUSTER_SECRETS_SOPS) from template"; \
	fi
	@if [ ! -f "$(SOPS_AGE_KEY_FILE)" ]; then \
		echo "Missing age key $(SOPS_AGE_KEY_FILE); run 'make secrets-create-key' first"; \
		exit 1; \
	fi
	@status=0; \
	SOPS_AGE_KEY_FILE="$(SOPS_AGE_KEY_FILE)" $(SOPS) "$(CLUSTER_SECRETS_SOPS)" || status=$$?; \
	if [ $$status -ne 0 ] && [ $$status -ne 200 ]; then \
		exit $$status; \
	fi

secrets-apply: ## Decrypt the cluster secrets and apply them to the cluster
	@if [ ! -f "$(CLUSTER_SECRETS_SOPS)" ]; then \
		echo "Missing $(CLUSTER_SECRETS_SOPS); run 'make secrets-edit' first"; \
		exit 1; \
	fi
	@if [ ! -f "$(SOPS_AGE_KEY_FILE)" ]; then \
		echo "Missing age key $(SOPS_AGE_KEY_FILE); run 'make secrets-create-key' first"; \
		exit 1; \
	fi
	SOPS_AGE_KEY_FILE="$(SOPS_AGE_KEY_FILE)" $(SOPS) -d "$(CLUSTER_SECRETS_SOPS)" | $(KUBECTL) apply -f -

secrets-create-key: ## Generate an age key for SOPS (prints the recipient)
	@if [ -f "$(SOPS_AGE_KEY_FILE)" ]; then \
		echo "Age key already exists at $(SOPS_AGE_KEY_FILE)"; \
	else \
		$(AGE_KEYGEN) -o "$(SOPS_AGE_KEY_FILE)"; \
		echo "Created $(SOPS_AGE_KEY_FILE)"; \
	fi

lint: ## Format all YAML with prettier, yamlfmt, then lint with yamllint
	$(PRETTIER) --write "**/*.{yaml,yml}"
	$(YAMLFMT) "**/*.{yaml,yml}"
	$(YAMLLINT) .

argo-sync: ## Force Argo CD Apps to refresh (kubectl; no argocd CLI). Use ARGOCD_SELECTOR=key=value to limit scope.
	@selector="$(ARGOCD_SELECTOR)"; \
	apps="$$( $(KUBECTL) -n argocd get applications $$([ -n "$$selector" ] && printf -- '-l %s' "$$selector") -o name )"; \
	if [ -z "$$apps" ]; then echo "No Applications matched."; exit 0; fi; \
	echo "$$apps" | xargs -n1 -I{} $(KUBECTL) -n argocd patch {} --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}' >/dev/null
