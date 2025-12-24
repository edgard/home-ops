#!/usr/bin/env bash
set -euo pipefail

# Configuration from environment
COMMAND="${1:-}"
DOCKER_HOST_SSH="${DOCKER_HOST_SSH:-}"
CLUSTER_NAME="${CLUSTER_NAME:-homelab}"
K3S_VERSION="${K3S_VERSION:-v1.33.6+k3s1}"
BWS_ACCESS_TOKEN="${BWS_ACCESS_TOKEN:-}"

KUBECONFIG_PATH="$HOME/.kube/config"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_CONTEXT_NAME="truenas"

# Storage paths on TrueNAS host
STORAGE_PATH="/mnt/spool/appdata"
MEDIA_PATH="/mnt/dpool/media"
KOPIA_PATH="/mnt/dpool/kopia-repo"
USB_DEVICE="/dev/ttyUSB0"

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
  DOCKER_HOST_SSH  - SSH connection string to TrueNAS (e.g., user@host.local)

Optional environment variables:
  CLUSTER_NAME     - Cluster name (default: homelab)
  K3S_VERSION      - K3s version (default: v1.33.6+k3s1)

Examples:
  DOCKER_HOST_SSH=edgard@sc01.home.arpa BWS_ACCESS_TOKEN=xxx $0 create
  DOCKER_HOST_SSH=edgard@sc01.home.arpa $0 destroy
  DOCKER_HOST_SSH=user@192.168.1.100 CLUSTER_NAME=mycluster $0 create
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
    echo "    Docker Host: ${DOCKER_HOST_SSH} (${DOCKER_HOST_IP})"
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

resolve_docker_host_ip() {
    echo "==> Resolving Docker host IP..."
    
    # Extract hostname from user@hostname format
    local hostname="${DOCKER_HOST_SSH#*@}"
    
    # Resolve hostname to IP address
    DOCKER_HOST_IP=$(getent hosts "$hostname" | awk '{ print $1 }' | head -n1)
    
    if [ -z "$DOCKER_HOST_IP" ]; then
        echo "ERROR: Could not resolve hostname '$hostname' to IP address"
        exit 1
    fi
    
    echo "✓ Resolved $hostname to $DOCKER_HOST_IP"
}

setup_docker_context() {
    echo "==> Setting up Docker context..."
    
    # Create or update Docker context for remote TrueNAS
    if docker context inspect "$DOCKER_CONTEXT_NAME" &> /dev/null; then
        echo "   Docker context '$DOCKER_CONTEXT_NAME' already exists"
    else
        docker context create "$DOCKER_CONTEXT_NAME" --docker "host=ssh://${DOCKER_HOST_SSH}"
        echo "✓ Docker context created"
    fi
    
    docker context use "$DOCKER_CONTEXT_NAME"
    echo "✓ Using Docker context: $DOCKER_CONTEXT_NAME"
}

verify_storage_paths() {
    echo "==> Verifying storage paths on TrueNAS..."
    
    ssh "$DOCKER_HOST_SSH" "test -d $STORAGE_PATH" || {
        echo "ERROR: Storage path $STORAGE_PATH does not exist on TrueNAS"
        exit 1
    }
    
    ssh "$DOCKER_HOST_SSH" "test -d $MEDIA_PATH" || {
        echo "ERROR: Media path $MEDIA_PATH does not exist on TrueNAS"
        exit 1
    }
    
    ssh "$DOCKER_HOST_SSH" "test -d $KOPIA_PATH" || {
        echo "ERROR: Kopia path $KOPIA_PATH does not exist on TrueNAS"
        exit 1
    }
    
    if ssh "$DOCKER_HOST_SSH" "test -c $USB_DEVICE"; then
        echo "✓ USB device $USB_DEVICE found"
    else
        echo "⚠ WARNING: USB device $USB_DEVICE not found (Zigbee2MQTT will not work)"
    fi
    
    echo "✓ Storage paths verified"
}

create_k3d_cluster() {
    echo "==> Creating k3d cluster '${CLUSTER_NAME}'..."
    
    k3d cluster create "$CLUSTER_NAME" \
        --servers 1 \
        --agents 1 \
        --api-port "${DOCKER_HOST_IP}:6443" \
        --port "8080:80@loadbalancer" \
        --port "8443:443@loadbalancer" \
        --volume "${STORAGE_PATH}:${STORAGE_PATH}@agent:*" \
        --volume "${MEDIA_PATH}:${MEDIA_PATH}@agent:*" \
        --volume "${KOPIA_PATH}:${KOPIA_PATH}@agent:*" \
        --volume "${USB_DEVICE}:${USB_DEVICE}@agent:*" \
        --k3s-arg "--disable=traefik@server:*" \
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
    require_env "DOCKER_HOST_SSH"

    ensure_tool "k3d" "brew install k3d"
    ensure_tool "kubectl" "brew install kubectl"
    ensure_tool "helmfile" "brew install helmfile"
    ensure_tool "docker" "brew install docker"

    resolve_docker_host_ip
    print_header "Bootstrap k3d Cluster"

    setup_docker_context
    verify_storage_paths
    
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
    require_env "DOCKER_HOST_SSH"

    resolve_docker_host_ip
    print_header "Destroy k3d Cluster"

    setup_docker_context
    
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
