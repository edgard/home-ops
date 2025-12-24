#!/usr/bin/env bash
set -euo pipefail

# Configuration from environment
COMMAND="${1:-}"
TARGET_HOST="${TARGET_HOST:-}"
CLUSTER_NAME="${CLUSTER_NAME:-homelab}"
K3S_VERSION="${K3S_VERSION:-v1.34.3+k3s1}"
SSH_USER="${SSH_USER:-root}"
BWS_ACCESS_TOKEN="${BWS_ACCESS_TOKEN:-}"

KUBECONFIG_PATH="$HOME/.kube/config"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_OPTS="-o StrictHostKeyChecking=no"

ssh_target() {
    ssh $SSH_OPTS "${SSH_USER}@${TARGET_HOST}" "$@"
}

confirm() {
    local message="$1"
    echo "$message"
    read -p "Continue? (y/N) " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]] || { echo "Aborted"; exit 1; }
}

cleanup_kubeconfig() {
    if [ -f "$KUBECONFIG_PATH" ] && command -v kubectl &> /dev/null; then
        kubectl config delete-context "$CLUSTER_NAME" 2>/dev/null || true
        kubectl config delete-cluster "$CLUSTER_NAME" 2>/dev/null || true
        kubectl config delete-user "$CLUSTER_NAME" 2>/dev/null || true
    fi
}

usage() {
    cat << EOF
Usage: $0 <command>

Commands:
  create    - Bootstrap K3s cluster and deploy platform components
  destroy   - Uninstall K3s from target host
  recreate  - Destroy and recreate cluster (destroy + create)
  update    - Update K3s to specified version

Required environment variables:
  TARGET_HOST      - IP or hostname of target server
  BWS_ACCESS_TOKEN - Bitwarden Secrets Manager token (create/recreate only)

Optional environment variables:
  CLUSTER_NAME - Cluster name (default: homelab)
  K3S_VERSION  - K3s version (default: v1.34.3+k3s1)
  SSH_USER     - SSH user (default: root)

Examples:
  TARGET_HOST=192.168.1.100 BWS_ACCESS_TOKEN=xxx $0 create
  TARGET_HOST=192.168.1.100 $0 destroy
  TARGET_HOST=192.168.1.100 K3S_VERSION=v1.35.0+k3s1 $0 update
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
    echo "    Target: ${SSH_USER}@${TARGET_HOST} | Cluster: ${CLUSTER_NAME} | Version: ${K3S_VERSION}"
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

ensure_target_prerequisites() {
    echo "==> Checking target host prerequisites..."

    if ssh_target "! command -v curl &> /dev/null || ! command -v iptables &> /dev/null || ! command -v modprobe &> /dev/null"; then
        echo "==> Installing prerequisites (curl, kmod, iptables)..."
        ssh_target "apt-get update -qq && apt-get install -y curl kmod iptables"
    fi

    echo "✓ Prerequisites available"
}

ensure_containerd_config() {
    echo "==> Configuring containerd for container environment..."
    ssh_target "mkdir -p /var/lib/rancher/k3s/agent/etc/containerd && cat > /var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl << 'EOF'
# Extends K3s base template to disable unprivileged_ports sysctl for systemd-nspawn
{{ template \"base\" . }}

[plugins.'io.containerd.cri.v1.runtime']
  enable_unprivileged_ports = false
EOF
"
    echo "✓ Containerd configured"
}

run_k3sup_install() {
    local action="${1:-Installing}"

    ensure_tool "k3sup" "curl -sLS https://get.k3sup.dev | sh && sudo install k3sup /usr/local/bin/"
    ensure_target_prerequisites
    ensure_containerd_config
    mkdir -p "$(dirname "$KUBECONFIG_PATH")"

    echo "==> ${action} K3s ${K3S_VERSION}..."
    k3sup install \
        --ip "$TARGET_HOST" \
        --user "$SSH_USER" \
        --k3s-version "$K3S_VERSION" \
        --cluster \
        --merge \
        --local-path "$KUBECONFIG_PATH" \
        --context "$CLUSTER_NAME" \
        --k3s-extra-args '--disable traefik --kubelet-arg=feature-gates=KubeletInUserNamespace=true'

    echo "✓ ${action} complete"
}

wait_for_resource() {
    local description="$1"
    local check_command="$2"
    local max_attempts=30
    local attempt=0

    echo "==> Waiting for ${description}..."

    # Give k3s a moment to fully initialize after k3sup
    sleep 3

    while [ $attempt -lt $max_attempts ]; do
        if eval "$check_command" 2>&1 | grep -v "Unable to connect" > /dev/null; then
            echo "✓ ${description} ready"
            return 0
        fi
        attempt=$((attempt + 1))
        echo "   Attempt $attempt/$max_attempts..."
        sleep 2
    done

    echo "ERROR: ${description} not ready after $max_attempts attempts"
    return 1
}

wait_for_api_server() {
    # Wait for API server to be responsive
    wait_for_resource "K3s API server" "ssh_target 'kubectl get --raw /healthz'"

    # Verify kubeconfig works locally
    export KUBECONFIG="$KUBECONFIG_PATH"
    kubectl config use-context "$CLUSTER_NAME" > /dev/null 2>&1

    wait_for_resource "kube-system service account" "kubectl get serviceaccount default -n kube-system"
}

cmd_create() {
    require_env "TARGET_HOST"
    require_env "BWS_ACCESS_TOKEN"

    ensure_tool "kubectl"
    ensure_tool "helmfile"

    print_header "Bootstrap K3s Cluster"

    cleanup_kubeconfig
    run_k3sup_install "Installing"

    echo "==> Deploying platform components..."
    export KUBECONFIG="$KUBECONFIG_PATH" BWS_ACCESS_TOKEN
    kubectl config use-context "$CLUSTER_NAME" > /dev/null

    wait_for_api_server

    cd "$SCRIPT_DIR"
    helmfile -f helmfile.yaml.gotmpl sync

    echo "✓ Bootstrap complete"
    echo "  kubectl config use-context ${CLUSTER_NAME}"
}

cmd_destroy() {
    require_env "TARGET_HOST"
    print_header "Destroy K3s Cluster"

    confirm "⚠ This will uninstall K3s from ${TARGET_HOST}"

    echo "==> Uninstalling K3s..."
    ssh_target << 'EOF'
if [ -f /usr/local/bin/k3s-uninstall.sh ]; then
    /usr/local/bin/k3s-killall.sh || true
    sleep 10
    /usr/local/bin/k3s-uninstall.sh || true
else
    echo "⚠ K3s not found"
fi
EOF

    cleanup_kubeconfig

    echo "✓ Destroy complete"
}

cmd_recreate() {
    cmd_destroy
    cmd_create
}

cmd_update() {
    require_env "TARGET_HOST"
    ensure_tool "kubectl"

    print_header "Update K3s Cluster"

    [ -f "$KUBECONFIG_PATH" ] || { echo "ERROR: Kubeconfig not found - run 'create' first"; exit 1; }

    export KUBECONFIG="$KUBECONFIG_PATH"
    CURRENT_VERSION=$(kubectl get node -o jsonpath='{.items[0].status.nodeInfo.kubeletVersion}' 2>/dev/null || echo "unknown")

    echo "Current: ${CURRENT_VERSION} → Target: ${K3S_VERSION}"

    if [ "$CURRENT_VERSION" = "$K3S_VERSION" ]; then
        confirm "⚠ Already at ${K3S_VERSION}"
    fi

    run_k3sup_install "Upgrading"

    NEW_VERSION=$(kubectl get node -o jsonpath='{.items[0].status.nodeInfo.kubeletVersion}' 2>/dev/null || echo "unknown")
    echo "✓ Update complete"
    echo "  Version: ${NEW_VERSION}"
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
    update)
        cmd_update
        ;;
    *)
        usage
        ;;
esac
