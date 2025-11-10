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
ARGO_ROOT_APP  ?= home-ops-root
ARGO_ADMIN_SECRET_NAME ?= argocd-initial-admin-secret

APP            ?= $(ARGO_ROOT_APP)

.PHONY: help bootstrap bootstrap-delete bootstrap-recreate kind-create kind-delete kind-recreate kind-status \
    argo-apps argo-sync argo-port-forward argo-admin-secret

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

argo-admin-secret: ## Print the argocd-initial-admin-secret password
	@set -euo pipefail; \
	secret_data="$$( $(KUBECTL) -n $(ARGOCD_NAMESPACE) get secret $(ARGO_ADMIN_SECRET_NAME) -o jsonpath='{.data.password}' 2>/dev/null )"; \
	if [ -z "$$secret_data" ]; then \
		echo "Secret $(ARGO_ADMIN_SECRET_NAME) not found in namespace $(ARGOCD_NAMESPACE)" >&2; \
		exit 1; \
	fi; \
	password="$$(printf "%s" "$$secret_data" | tr -d '\n' | openssl base64 -d -A)"; \
	echo "$$password"
