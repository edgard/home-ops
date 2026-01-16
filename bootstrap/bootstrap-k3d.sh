#!/usr/bin/env bash
set -euo pipefail

# Configuration from environment
COMMAND="${1:-}"
DOCKER_HOST="${DOCKER_HOST:-}"
CLUSTER_NAME="${CLUSTER_NAME:-homelab}"
K3S_VERSION="${K3S_VERSION:-v1.33.6-k3s1}"
BWS_ACCESS_TOKEN="${BWS_ACCESS_TOKEN:-}"

KUBECONFIG_PATH="$HOME/.kube/config"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Volume mounts for k3d server (path:path format)
# Note: ZFS child datasets must be mounted explicitly
VOLUME_MOUNTS=(
    "/mnt/spool/appdata:/mnt/spool/appdata"
    "/mnt/dpool/media:/mnt/dpool/media"
    "/mnt/dpool/restic:/mnt/dpool/restic"
    "/dev/ttyUSB0:/dev/ttyUSB0"
    "/dev/ttyUSB1:/dev/ttyUSB1"
)

confirm() {
    local message="$1"
    echo "$message"
    read -p "Continue? (y/N) " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]] || { echo "Aborted"; exit 1; }
}

cleanup_kubeconfig() {
    if [ -f "$KUBECONFIG_PATH" ] && command -v kubectl &> /dev/null; then
        kubectl config delete-context "k3d-${CLUSTER_NAME}" 2>/dev/null || true
        kubectl config delete-cluster "k3d-${CLUSTER_NAME}" 2>/dev/null || true
        kubectl config delete-user "admin@k3d-${CLUSTER_NAME}" 2>/dev/null || true
    fi
}

usage() {
    cat << EOF
Usage: $0 <command>

Commands:
  create    - Bootstrap k3d cluster and deploy platform components
  destroy   - Delete k3d cluster
  recreate  - Destroy and recreate cluster (destroy + create)

Required environment variables:
  BWS_ACCESS_TOKEN - Bitwarden Secrets Manager token (create/recreate only)
  DOCKER_HOST      - Docker host SSH connection (e.g., ssh://edgard@192.168.1.254)

Optional environment variables:
  CLUSTER_NAME     - Cluster name (default: homelab)
  K3S_VERSION      - K3s version (default: v1.33.6-k3s1)

Examples:
  DOCKER_HOST=ssh://edgard@192.168.1.254 BWS_ACCESS_TOKEN=xxx $0 create
  DOCKER_HOST=ssh://edgard@192.168.1.254 $0 destroy
EOF
    exit 1
}

require_env() {
    local var_name="$1"
    local var_value="${!var_name}"
    [ -n "$var_value" ] || { echo "ERROR: $var_name is required"; exit 1; }
}

print_header() {
    local title="$1"
    echo "==> $title"
    echo "    Docker Host: ${DOCKER_HOST}"
    echo "    Cluster: ${CLUSTER_NAME} | K3s: ${K3S_VERSION}"
    echo ""
}

ensure_tool() {
    local tool="$1"
    local install_hint="${2:-}"

    if ! command -v "$tool" &> /dev/null; then
        echo "ERROR: $tool is not installed"
        [ -n "$install_hint" ] && echo "Install with: $install_hint"
        exit 1
    fi
}

create_k3d_cluster() {
    echo "==> Creating k3d cluster '${CLUSTER_NAME}'..."
    
    # Using host network mode - no separate Docker network needed
    echo "==> Using host network mode (br0 via host namespace)"
    
    # Build volume mount arguments
    local volume_args=()
    for mount in "${VOLUME_MOUNTS[@]}"; do
        volume_args+=(--volume "${mount}")
    done
    
    k3d cluster create "$CLUSTER_NAME" \
        --network host \
        --servers 1 \
        --agents 0 \
        "${volume_args[@]}" \
        --k3s-arg "--disable=traefik" \
        --image "rancher/k3s:${K3S_VERSION}"
    
    echo "✓ k3d cluster created"
}

wait_for_resource() {
    local description="$1"
    local check_command="$2"
    local max_attempts=30
    local attempt=0

    echo -n "==> Waiting for ${description}..."

    while [ $attempt -lt $max_attempts ]; do
        if eval "$check_command" &> /dev/null; then
            echo " ✓"
            return 0
        fi
        attempt=$((attempt + 1))
        echo -n "."
        sleep 2
    done

    echo " ✗"
    echo "ERROR: ${description} not ready after $max_attempts attempts"
    return 1
}

cmd_create() {
    require_env "BWS_ACCESS_TOKEN"
    require_env "DOCKER_HOST"

    ensure_tool "k3d" "brew install k3d"
    ensure_tool "kubectl" "brew install kubectl"
    ensure_tool "helmfile" "brew install helmfile"
    ensure_tool "docker" "brew install docker"

    print_header "Bootstrap k3d Cluster"
    
    cleanup_kubeconfig
    create_k3d_cluster
    
    # Switch to k3d cluster context
    export KUBECONFIG="$KUBECONFIG_PATH"
    kubectl config use-context "k3d-${CLUSTER_NAME}" > /dev/null
    
    wait_for_resource "k3d API server" "kubectl get nodes"
    wait_for_resource "kube-system service account" "kubectl get serviceaccount default -n kube-system"

    echo "==> Deploying platform components..."
    export BWS_ACCESS_TOKEN
    cd "$SCRIPT_DIR"
    helmfile -f helmfile.yaml.gotmpl sync

    echo "✓ Bootstrap complete"
    echo "  kubectl config use-context k3d-${CLUSTER_NAME}"
}

cmd_destroy() {
    require_env "DOCKER_HOST"

    print_header "Destroy k3d Cluster"
    
    confirm "⚠ This will delete the k3d cluster '${CLUSTER_NAME}'"

    echo "==> Deleting k3d cluster..."
    k3d cluster delete "$CLUSTER_NAME" || echo "⚠ Cluster not found or already deleted"

    cleanup_kubeconfig

    echo "✓ Destroy complete"
}

cmd_recreate() {
    cmd_destroy
    cmd_create
}

case "$COMMAND" in
    create)
        cmd_create
        ;;
    destroy)
        cmd_destroy
        ;;
    recreate)
        cmd_recreate
        ;;
    *)
        usage
        ;;
esac
