# ---- Makefile for Flux-managed Kind homelab ---------------------------------
.DEFAULT_GOAL := help

REPO_ROOT      := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
BOOTSTRAP      ?= $(REPO_ROOT)bootstrap/bootstrap.sh
KIND           ?= kind
KIND_CONFIG    ?= $(REPO_ROOT)bootstrap/cluster-config.yaml
KIND_CONFIG_NAME := $(shell awk '/^name:[[:space:]]*/ {sub(/^name:[[:space:]]*/, ""); print; exit}' "$(KIND_CONFIG)" 2>/dev/null)
CLUSTER_NAME   ?= $(if $(KIND_CONFIG_NAME),$(KIND_CONFIG_NAME),homelab)
KUBECTL        ?= kubectl
FLUX           ?= flux
SOPS           ?= sops
AGE_KEYGEN     ?= age-keygen
SOPS_AGE_KEY_FILE ?= $(REPO_ROOT).sops.agekey
GIT_CREDENTIALS_FILE ?= $(REPO_ROOT).git-credentials

SOPS_FIND      ?= find $(REPO_ROOT) -type f \
	\( -name '*.sops.yaml' -o -name '*.sops.yml' -o -name '*.sops.json' \) \
	! -name '.sops.yaml'
KS_SOURCE      ?= flux-system
KS_NAME        ?= cluster-apps
KS_NAMESPACE   ?= flux-system
TARGET         ?=

ifeq ($(wildcard $(SOPS_AGE_KEY_FILE)), $(SOPS_AGE_KEY_FILE))
export SOPS_AGE_KEY_FILE := $(SOPS_AGE_KEY_FILE)
endif

.PHONY: help bootstrap bootstrap-delete bootstrap-recreate kind-create kind-delete kind-recreate kind-status flux-check flux-status \
    flux-reconcile flux-alerts render validate require-target \
    sops-list sops-validate sops-edit sops-encrypt sops-decrypt sops-key-generate sops-key-show \
    sops-key-delete

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "}; /^[a-zA-Z0-9_\-]+:.*?## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo "\nVariables:"
	@echo "  CLUSTER_NAME=$(CLUSTER_NAME)  KIND_CONFIG=$(KIND_CONFIG)"
	@echo "  KS_SOURCE=$(KS_SOURCE)  KS_NAME=$(KS_NAME)  KS_NAMESPACE=$(KS_NAMESPACE)"
	@echo "  SOPS_AGE_KEY_FILE=$(SOPS_AGE_KEY_FILE)"
	@echo "  GIT_CREDENTIALS_FILE=$(GIT_CREDENTIALS_FILE)"
	@echo "  TARGET=$(TARGET)"

bootstrap: ## Provision Kind cluster on remote Docker host and install Flux
	@if [ -f "$(SOPS_AGE_KEY_FILE)" ]; then export SOPS_AGE_KEY_FILE="$(SOPS_AGE_KEY_FILE)"; fi; \
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

flux-check: ## Verify Flux prerequisites and controllers
	$(FLUX) check --pre
	$(FLUX) check

flux-status: ## Show status for all Flux kustomizations
	$(FLUX) get kustomizations -A

flux-reconcile: ## Force reconcile of the primary Git source and kustomization
	$(FLUX) reconcile source git "$(KS_SOURCE)" --namespace "$(KS_NAMESPACE)"
	$(FLUX) reconcile kustomization "$(KS_NAME)" --namespace "$(KS_NAMESPACE)"

flux-alerts: ## Show registered Flux alerts
	$(FLUX) get alert -n $(KS_NAMESPACE)

render: require-target ## Render a kustomization (set TARGET=path)
	$(KUBECTL) kustomize "$(TARGET)"

validate: require-target ## Server-side dry-run apply of a kustomization (set TARGET=path)
	$(KUBECTL) apply --server-side --dry-run=client -k "$(TARGET)"

sops-list: ## List tracked SOPS-encrypted files
	@$(SOPS_FIND) | sort || true

sops-validate: ## Attempt to decrypt all SOPS files to validate keys
	@files="$$( $(SOPS_FIND) 2>/dev/null )"; \
	if [ -z "$$files" ]; then \
	  echo "No SOPS-managed files found."; \
	else \
	  for f in $$files; do \
	    printf 'Checking %s\n' "$$f"; \
	    $(SOPS) -d "$$f" >/dev/null; \
	  done; \
	fi

sops-edit: require-target ## Open a SOPS file for editing (set TARGET=path)
	$(SOPS) "$(TARGET)"

sops-encrypt: require-target ## Encrypt or re-encrypt a file in place (set TARGET=path)
	$(SOPS) --encrypt --in-place "$(TARGET)"

sops-decrypt: require-target ## Print decrypted contents to stdout (set TARGET=path)
	$(SOPS) --decrypt "$(TARGET)"

sops-key-generate: ## Generate an Age key for SOPS at SOPS_AGE_KEY_FILE
	@if [ -f "$(SOPS_AGE_KEY_FILE)" ]; then \
	  echo "Key already exists at $(SOPS_AGE_KEY_FILE). Remove it first with make sops-key-delete."; \
	  exit 1; \
	fi
	@mkdir -p "$(dir $(SOPS_AGE_KEY_FILE))"
	$(AGE_KEYGEN) -o "$(SOPS_AGE_KEY_FILE)"
	@chmod 600 "$(SOPS_AGE_KEY_FILE)"
	@printf "Generated Age key at %s\nPublic key:\n" "$(SOPS_AGE_KEY_FILE)"
	@$(AGE_KEYGEN) -y "$(SOPS_AGE_KEY_FILE)"

sops-key-show: ## Print the Age public key derived from SOPS_AGE_KEY_FILE
	@test -f "$(SOPS_AGE_KEY_FILE)" || (echo "Missing $(SOPS_AGE_KEY_FILE). Generate one with make sops-key-generate." && exit 1)
	@$(AGE_KEYGEN) -y "$(SOPS_AGE_KEY_FILE)"

sops-key-delete: ## Remove the local Age key file (manual cleanup)
	@if [ -f "$(SOPS_AGE_KEY_FILE)" ]; then \
	  rm -f "$(SOPS_AGE_KEY_FILE)"; \
	  echo "Removed $(SOPS_AGE_KEY_FILE)"; \
	else \
	  echo "No key found at $(SOPS_AGE_KEY_FILE)"; \
	fi

require-target:
	@test -n "$(TARGET)" || (echo "Set TARGET=relative/path/to/kustomization"; exit 1)
