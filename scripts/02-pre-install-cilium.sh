#!/usr/bin/env bash

kubectl create namespace kube-system --dry-run=client -o yaml | kubectl apply -f -
helm repo add cilium https://helm.cilium.io && helm repo update && helm install cilium cilium/cilium --namespace kube-system --set operator.replicas=1
cilium status --wait
kubectl get pods --all-namespaces -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,HOSTNETWORK:.spec.hostNetwork --no-headers=true | grep '<none>' | awk '{print "-n "$1" "$2}' | xargs -L 1 -r kubectl delete pod
