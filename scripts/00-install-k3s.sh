#!/usr/bin/env bash

curl -sfL https://get.k3s.io | INSTALL_K3S_CHANNEL=stable INSTALL_K3S_SYMLINK=skip INSTALL_K3S_EXEC="--write-kubeconfig-mode 0644 --disable local-storage --disable traefik --disable servicelb" sh -s -
