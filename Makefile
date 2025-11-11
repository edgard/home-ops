# ---- Makefile for Argo CD-managed Kind homelab ------------------------------
.DEFAULT_GOAL := help

REPO_ROOT      := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
BOOTSTRAP      ?= $(REPO_ROOT)bootstrap/bootstrap.sh
KIND           ?= kind
KIND_CONFIG    ?= $(REPO_ROOT)bootstrap/cluster-config.yaml
KIND_CONFIG_NAME := $(shell awk '/^name:[[:space:]]*/ {sub(/^name:[[:space:]]*/, ""); print; exit}' "$(KIND_CONFIG)" 2>/dev/null)
CLUSTER_NAME   ?= $(if $(KIND_CONFIG_NAME),$(KIND_CONFIG_NAME),homelab)
KUBECTL        ?= kubectl
ARGOCD_NAMESPACE ?= argocd
ARGO_ROOT_APP  ?= homelab-root

APP            ?= $(ARGO_ROOT_APP)
SOPS           ?= sops
SOPS_AGE_KEY_FILE ?= $(REPO_ROOT).sops.agekey
CENTRAL_SECRETS_SOPS ?= $(REPO_ROOT)bootstrap/central-secrets.sops.yaml
CENTRAL_SECRETS_TEMPLATE ?= $(REPO_ROOT)bootstrap/central-secrets.template.yaml
AGE_KEYGEN     ?= age-keygen

.PHONY: help bootstrap bootstrap-delete bootstrap-recreate kind-create kind-delete kind-recreate kind-status \
    argo-apps argo-sync argo-port-forward secrets-edit secrets-apply secrets-create-key

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "}; /^[a-zA-Z0-9_\-]+:.*?## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo "\nVariables:"
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

argo-apps: ## List Argo CD applications
	$(KUBECTL) -n $(ARGOCD_NAMESPACE) get applications

argo-sync: ## Force a hard refresh of APP (default $(ARGO_ROOT_APP))
	@test -n "$(APP)" || (echo "Set APP=<application-name>"; exit 1)
	$(KUBECTL) -n $(ARGOCD_NAMESPACE) patch application "$(APP)" --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'

argo-port-forward: ## Forward Argo CD UI to localhost:8080
	$(KUBECTL) -n $(ARGOCD_NAMESPACE) port-forward svc/argocd-server 8080:80

secrets-edit: ## Create or edit the encrypted central secrets with SOPS
	@if [ ! -f "$(CENTRAL_SECRETS_SOPS)" ]; then \
		if [ ! -f "$(CENTRAL_SECRETS_TEMPLATE)" ]; then \
			echo "Template $(CENTRAL_SECRETS_TEMPLATE) not found"; \
			exit 1; \
		fi; \
		cp "$(CENTRAL_SECRETS_TEMPLATE)" "$(CENTRAL_SECRETS_SOPS)"; \
		echo "Created $(CENTRAL_SECRETS_SOPS) from template"; \
	fi
	@if [ ! -f "$(SOPS_AGE_KEY_FILE)" ]; then \
		echo "Missing age key $(SOPS_AGE_KEY_FILE); run 'make secrets-create-key' first"; \
		exit 1; \
	fi
	@status=0; \
	SOPS_AGE_KEY_FILE="$(SOPS_AGE_KEY_FILE)" $(SOPS) "$(CENTRAL_SECRETS_SOPS)" || status=$$?; \
	if [ $$status -ne 0 ] && [ $$status -ne 200 ]; then \
		exit $$status; \
	fi

secrets-apply: ## Decrypt the central secrets and apply them to the cluster
	@if [ ! -f "$(CENTRAL_SECRETS_SOPS)" ]; then \
		echo "Missing $(CENTRAL_SECRETS_SOPS); run 'make secrets-edit' first"; \
		exit 1; \
	fi
	@if [ ! -f "$(SOPS_AGE_KEY_FILE)" ]; then \
		echo "Missing age key $(SOPS_AGE_KEY_FILE); run 'make secrets-create-key' first"; \
		exit 1; \
	fi
	SOPS_AGE_KEY_FILE="$(SOPS_AGE_KEY_FILE)" $(SOPS) -d "$(CENTRAL_SECRETS_SOPS)" | $(KUBECTL) apply -f -

secrets-create-key: ## Generate an age key for SOPS (prints the recipient)
	@if [ -f "$(SOPS_AGE_KEY_FILE)" ]; then \
		echo "Age key already exists at $(SOPS_AGE_KEY_FILE)"; \
	else \
		$(AGE_KEYGEN) -o "$(SOPS_AGE_KEY_FILE)"; \
		echo "Created $(SOPS_AGE_KEY_FILE)"; \
	fi
