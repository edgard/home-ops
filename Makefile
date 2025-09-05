# ---- Makefile for single Docker Compose stack (home) ------------------------
.DEFAULT_GOAL := help

# Core inputs
STACK        ?= home
FILES        ?= compose.$(STACK).yml     # supports space-separated list
DETACH       ?= -d
SERVICE      ?=
LOGS_TAIL    ?= 200
SINCE        ?=                          # e.g. 1h or 2024-09-01T00:00:00

# Compose binary
COMPOSE      ?= docker compose

# Extra env file: Compose already loads .env by default
ENV_OPTS := $(if $(wildcard .env.$(STACK)),--env-file .env.$(STACK),)

# Build common CLI option groups
FOPTS        := $(foreach f,$(FILES),-f $(f))

# Convenience: base compose command with consistent options
CBASE        := $(COMPOSE) $(ENV_OPTS) $(FOPTS)

# Internal helpers
_service     = $(if $(SERVICE),$(SERVICE),)
_logs_since  = $(if $(SINCE),--since $(SINCE),)

.PHONY: help env-check file-check config up down restart ps logs pull build recreate update exec prune

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "}; /^[a-zA-Z0-9_\-]+:.*?## / {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo "\nVariables:"
	@echo "  STACK=$(STACK)  FILES=$(FILES)"
	@echo "  SERVICE=$(SERVICE)  DETACH=$(DETACH)  LOGS_TAIL=$(LOGS_TAIL)  SINCE=$(SINCE)"

env-check: ## Show which env files are being used
	@echo "ENV files loaded:"
	@([ -f .env ] && echo "  .env (auto)") || true
	@([ -f .env.$(STACK) ] && echo "  .env.$(STACK) (via --env-file)") || true
	@([ -f .env ] || [ -f .env.$(STACK) ]) || echo "  (none found)"
	@echo "Compose command: $(COMPOSE)"

file-check: ## Verify compose file(s) exist
	@missing=0; \
	for f in $(FILES); do \
	  if [ ! -f $$f ]; then echo "Missing compose file: $$f"; missing=1; fi; \
	done; \
	if [ $$missing -ne 0 ]; then exit 1; fi
	@echo "Using compose files: $(FILES)"

config: file-check ## Show the fully rendered config
	$(CBASE) config

up: file-check ## Start (or create) the stack
	$(CBASE) up $(DETACH) --remove-orphans

down: file-check ## Stop and remove containers
	$(CBASE) down

restart: file-check ## Restart the whole stack or a SERVICE=...
	$(CBASE) restart $(_service)

ps: file-check ## Show containers
	$(CBASE) ps

logs: file-check ## Tail logs (use SERVICE=name and/or SINCE=1h)
	$(CBASE) logs -f $(_logs_since) --tail=$(LOGS_TAIL) $(_service)

pull: file-check ## Pull images
	$(CBASE) pull $(_service)

build: file-check ## Build images (if any build sections exist)
	$(CBASE) build $(_service)

recreate: file-check ## Recreate containers (no image pull)
	$(CBASE) up $(DETACH) --force-recreate

update: file-check ## Pull images and (re)create containers
	$(CBASE) pull
	$(CBASE) up $(DETACH)

exec: file-check ## Exec into a container: SERVICE=name make exec CMD="/bin/sh"
	@test -n "$(SERVICE)" || (echo "Set SERVICE=name"; exit 1)
	$(CBASE) exec $(SERVICE) $(if $(CMD),$(CMD),/bin/sh)

prune: ## Cleanup unused Docker resources
	@docker system prune -a --volumes -f
	@docker builder prune -a -f || true
