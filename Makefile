# ---- Makefile for single Docker Compose stack (home) ------------------------
STACK       ?= home
FILES       ?= compose.$(STACK).yml
DETACH      ?= -d
SERVICE     ?=
LOGS_TAIL   ?= 200

COMPOSE     ?= docker compose

# Auto-load env files if they exist
ENV_OPTS := $(if $(wildcard .env),--env-file .env,) \
            $(if $(wildcard .env.$(STACK)),--env-file .env.$(STACK),)

# Internal: pass a service name only if provided
_service    = $(if $(SERVICE),$(SERVICE),)

.PHONY: help up down stop restart ps logs pull build recreate update config \
        prune orphans exec sh top events images volumes env-check file-check

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "}; /^[a-zA-Z0-9_\-]+:.*?## / {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

env-check: ## Show which env files are being used
	@echo "ENV files loaded:"
	@([ -f .env ] && echo "  .env") || true
	@([ -f .env.$(STACK) ] && echo "  .env.$(STACK)") || true
	@([ -f .env ] || [ -f .env.$(STACK) ]) || echo "  (none found)"

file-check: ## Verify compose file exists
	@[ -f $(FILES) ] || (echo "Compose file '$(FILES)' not found" && exit 1)
	@echo "Using compose file: $(FILES)"

up: file-check ## Start (or create) the stack
	$(COMPOSE) $(ENV_OPTS) -f $(FILES) up $(DETACH) --remove-orphans

down: file-check ## Stop and remove containers
	$(COMPOSE) $(ENV_OPTS) -f $(FILES) down

stop: file-check ## Stop containers without removing
	$(COMPOSE) $(ENV_OPTS) -f $(FILES) stop $(_service)

restart: file-check ## Restart the whole stack or a SERVICE=...
	$(COMPOSE) $(ENV_OPTS) -f $(FILES) restart $(_service)

ps: file-check ## Show containers
	$(COMPOSE) $(ENV_OPTS) -f $(FILES) ps

logs: file-check ## Tail logs (use SERVICE=name to narrow)
	$(COMPOSE) $(ENV_OPTS) -f $(FILES) logs -f --tail=$(LOGS_TAIL) $(_service)

pull: file-check ## Pull images
	$(COMPOSE) $(ENV_OPTS) -f $(FILES) pull $(_service)

build: file-check ## Build images (if any build sections exist)
	$(COMPOSE) $(ENV_OPTS) -f $(FILES) build $(_service)

recreate: file-check ## Recreate containers (no image pull)
	$(COMPOSE) $(ENV_OPTS) -f $(FILES) up $(DETACH) --force-recreate

update: file-check ## Pull images and (re)create containers
	$(COMPOSE) $(ENV_OPTS) -f $(FILES) pull
	$(COMPOSE) $(ENV_OPTS) -f $(FILES) up $(DETACH)

config: file-check ## Show the fully rendered config
	$(COMPOSE) $(ENV_OPTS) -f $(FILES) config

prune: file-check ## Remove unused containers, images, networks, and volumes
	@docker system prune -a --volumes

exec: file-check ## Exec into a container: SERVICE=name make exec CMD="/bin/sh"
	@test -n "$(SERVICE)" || (echo "Set SERVICE=name"; exit 1)
	@$(if $(CMD),,$(eval CMD=/bin/sh))
	$(COMPOSE) $(ENV_OPTS) -f $(FILES) exec $(SERVICE) $(CMD)

sh: ## Shortcut for `exec` with /bin/sh
	@$(MAKE) exec SERVICE="$(SERVICE)" CMD="/bin/sh"

top: file-check ## Show running processes per container
	$(COMPOSE) $(ENV_OPTS) -f $(FILES) top

events: file-check ## Stream events
	$(COMPOSE) $(ENV_OPTS) -f $(FILES) events

images: file-check ## List images used by the stack
	$(COMPOSE) $(ENV_OPTS) -f $(FILES) images

volumes: file-check ## List volumes used by the stack
	$(COMPOSE) $(ENV_OPTS) -f $(FILES) ls --format table
