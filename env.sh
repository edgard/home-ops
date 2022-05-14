#!/usr/bin/env bash

export RENOVATE_TOKEN='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'
export RENOVATE_AUTODISCOVER='false'
export RENOVATE_PLATFORM='github'
export RENOVATE_CONFIG_FILE="/usr/src/app/config.json"

docker run -e RENOVATE_TOKEN -e RENOVATE_AUTODISCOVER -e RENOVATE_PLATFORM -e RENOVATE_CONFIG_FILE --rm -v "/home/edgard/projects/k8s-home-config/config.json:/usr/src/app/config.json" renovate/renovate
