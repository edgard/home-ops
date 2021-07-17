#!/usr/bin/env bash

curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 644 --disable traefik --disable local-storage
