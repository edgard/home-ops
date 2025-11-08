#!/usr/bin/env bash

set -euo pipefail

# User-configurable defaults (override via environment)
KUBECONFIG_PATH="${KUBECONFIG:-${HOME}/.kube/config}"
MULTUS_PARENT_IFACE="${MULTUS_PARENT_IFACE:-br0}"
MULTUS_PARENT_SUBNET="${MULTUS_PARENT_SUBNET:-192.168.1.0/24}"
MULTUS_PARENT_GATEWAY="${MULTUS_PARENT_GATEWAY:-192.168.1.1}"
MULTUS_PARENT_IP_RANGE="${MULTUS_PARENT_IP_RANGE:-192.168.1.240/29}"

# Internal constants derived from configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
KIND_CONFIG_PATH="${REPO_ROOT}/bootstrap/cluster-config.yaml"
SOPS_AGE_KEY_PATH="${REPO_ROOT}/.sops.agekey"
GIT_CREDENTIALS_PATH="${REPO_ROOT}/.git-credentials"

# Global variables
DELETE_MODE=false
CLUSTER_NAME=""
DOCKER_CONTEXT=""
MULTUS_NETWORK=""
BIND_ADDRESS=""
ADVERTISE_HOST=""
TEMP_CONFIG=""
ORIGINAL_CONTEXT=""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
_log() {
    local level="${1}" message="${2}" color="${3}"
    local timestamp prefix

    timestamp=$(date '+%H:%M:%S')
    prefix="[${timestamp}] ${level}"

    echo -e "\n${color}${prefix} ${message}${NC}" >&2
}

log() { _log "INFO" "${1}" "${GREEN}"; }
log_warn() { _log "WARN" "${1}" "${YELLOW}"; }
log_error() { _log "ERROR" "${1}" "${RED}"; }
fatal() {
    log_error "${1}"
    exit 1
}

# -----------------------------------------------------------------------------
# CLI parsing
# -----------------------------------------------------------------------------
show_usage() {
    cat <<EOF
Usage: $(basename "${0}") [OPTIONS]

Bootstrap the Kind-based homelab cluster or delete it.

OPTIONS:
    -d, --delete    Delete the Kind cluster instead of creating and bootstrapping it
    -h, --help      Show this help message and exit

ENVIRONMENT VARIABLES:
    KUBECONFIG      Path to kubeconfig file (default: ${KUBECONFIG_PATH})
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "${1}" in
        -d | --delete)
            DELETE_MODE=true
            ;;
        -h | --help)
            show_usage
            exit 0
            ;;
        *)
            fatal "CLI: Unknown option ${1}"
            ;;
        esac
        shift
    done
}

# -----------------------------------------------------------------------------
# General helpers
# -----------------------------------------------------------------------------
require() {
    if ! command -v "${1}" >/dev/null 2>&1; then
        fatal "Deps: ${1} is required but not found in PATH"
    fi
}

load_cluster_name() {
    local config_path="${1}"
    local name

    if [[ ! -f "${config_path}" ]]; then
        fatal "Config: Kind config ${config_path} does not exist"
    fi

    name=$(yq eval '.name' "${config_path}" 2>/dev/null)

    if [[ -z "${name}" || "${name}" == "null" ]]; then
        fatal "Config: Kind config ${config_path} does not define a cluster name"
    fi

    echo "${name}"
}

cluster_exists() {
    kind get clusters 2>/dev/null | grep -qx "${1}"
}

inspect_docker_host() {
    docker context inspect "${1}" --format '{{- if .Endpoints }}{{- with index .Endpoints "docker" }}{{ .Host }}{{ end }}{{- end }}' 2>/dev/null || true
}

cleanup() {
    [[ -n "${TEMP_CONFIG:-}" ]] && rm -f "${TEMP_CONFIG}"
    [[ -n "${ORIGINAL_CONTEXT:-}" ]] && docker context use "${ORIGINAL_CONTEXT}" 2>/dev/null || true
}

use_docker_context() {
    local target="${1}"
    ORIGINAL_CONTEXT=$(docker context show 2>/dev/null || echo "default")

    if [[ "${ORIGINAL_CONTEXT}" != "${target}" ]]; then
        log "Docker: Switching context to ${target}"
        docker context use "${target}"
    fi
}

# -----------------------------------------------------------------------------
# API server endpoint management
# -----------------------------------------------------------------------------
detect_api_endpoint_settings() {
    local docker_host remote_host

    if [[ -n "${ADVERTISE_HOST}" ]]; then
        return
    fi

    docker_host=$(inspect_docker_host "${DOCKER_CONTEXT}")
    case "${docker_host}" in
    tcp://*)
        remote_host="${docker_host#tcp://}"
        remote_host="${remote_host%%:*}"
        ;;
    ssh://*)
        remote_host="${docker_host#ssh://}"
        remote_host="${remote_host##*@}"
        remote_host="${remote_host%%:*}"
        ;;
    unix://* | npipe://* | "")
        remote_host=""
        ;;
    *)
        remote_host="${docker_host}"
        ;;
    esac

    if [[ "${remote_host}" =~ ^(127\.0\.0\.1|localhost)$ ]]; then
        remote_host=""
    fi

    BIND_ADDRESS=""
    ADVERTISE_HOST="${remote_host}"

    if [[ -n "${remote_host}" ]]; then
        BIND_ADDRESS="0.0.0.0"
        log "API: Exposing control plane on ${remote_host} (bind ${BIND_ADDRESS})"
    else
        log "API: Using local control plane endpoint"
    fi
}

patch_kubeconfig_endpoint() {
    local cluster_context="kind-${CLUSTER_NAME}"
    local server current_host port

    if [[ -z "${ADVERTISE_HOST}" ]]; then
        return
    fi

    if ! cluster_exists "${CLUSTER_NAME}"; then
        return
    fi

    if server=$(kubectl config view --raw -o json 2>/dev/null | yq -p=json -r ".clusters[] | select(.name==\"${cluster_context}\") | .cluster.server" 2>/dev/null); then
        if [[ "${server}" =~ ^https://([^:]+):(.+)$ ]]; then
            current_host="${BASH_REMATCH[1]}"
            port="${BASH_REMATCH[2]}"
            if [[ -n "${current_host}" && -n "${port}" && "${current_host}" != "${ADVERTISE_HOST}" ]]; then
                log "Kubeconfig: Patching server endpoint to https://${ADVERTISE_HOST}:${port}"
                kubectl config set-cluster "${cluster_context}" "--server=https://${ADVERTISE_HOST}:${port}"
            fi
        fi
    fi
}

# -----------------------------------------------------------------------------
# Flux and secret management
# -----------------------------------------------------------------------------
install_flux_release() {
    local release_name="${1}"
    local repo_manifest="${2}"
    local helmrelease_manifest="${3}"
    local chart_url chart_version

    chart_url=$(yq -r '.spec.url' "${repo_manifest}")
    chart_version=$(yq -r '.spec.ref.tag' "${repo_manifest}")

    if [[ -z "${chart_url}" || "${chart_url}" == "null" ]]; then
        fatal "Flux: Missing spec.url in ${repo_manifest}"
    fi

    if [[ -z "${chart_version}" || "${chart_version}" == "null" ]]; then
        fatal "Flux: Missing spec.ref.tag in ${repo_manifest}"
    fi

    log "Flux: Installing ${release_name} (${chart_url}@${chart_version})"
    helm upgrade --install "${release_name}" "${chart_url}" --namespace flux-system --create-namespace --version "${chart_version}" --values <(yq -o=yaml '.spec.values // {}' "${helmrelease_manifest}") --wait
}

setup_flux() {
    log "Flux: Running flux check --pre"
    flux check --pre || fatal "Flux: Pre-check failed"

    local manifests_root="${REPO_ROOT}/kubernetes/apps/flux-system"
    local -a releases=(
        "flux-operator:${manifests_root}/flux-operator/app"
        "flux-instance:${manifests_root}/flux-instance/app"
    )

    local release release_name release_path
    for release in "${releases[@]}"; do
        IFS=":" read -r release_name release_path <<<"${release}"
        install_flux_release "${release_name}" "${release_path}/ocirepository.yaml" "${release_path}/helmrelease.yaml"
    done

    log "Flux: Operator components installed"
}

apply_secret() {
    local namespace="${1}" secret_name="${2}"
    shift 2

    local -a create_args=("${@}")

    kubectl -n "${namespace}" create secret generic "${secret_name}" "${create_args[@]}" --dry-run=client -o yaml | kubectl apply -f -
}

create_flux_secrets() {
    local git_username git_pat
    local -a applied_secrets=()

    if [[ -f "${SOPS_AGE_KEY_PATH}" ]]; then
        apply_secret "flux-system" "sops-age" --from-file="age.agekey=${SOPS_AGE_KEY_PATH}"
        applied_secrets+=("sops-age")
    else
        log_warn "Secrets: Missing ${SOPS_AGE_KEY_PATH}; run make sops-key-generate"
    fi

    if [[ -f "${GIT_CREDENTIALS_PATH}" ]]; then
        git_username=$(grep '^username=' "${GIT_CREDENTIALS_PATH}" 2>/dev/null | cut -d= -f2- || true)
        git_pat=$(grep '^password=' "${GIT_CREDENTIALS_PATH}" 2>/dev/null | cut -d= -f2- || true)

        if [[ -n "${git_username}" && -n "${git_pat}" ]]; then
            apply_secret "flux-system" "home-ops-git" --from-literal="username=${git_username}" --from-literal="password=${git_pat}"
            applied_secrets+=("home-ops-git")
        else
            log_warn "Git: Incomplete credentials; add username= and password= lines"
        fi
    else
        log_warn "Git: Missing ${GIT_CREDENTIALS_PATH}; populate it with username=/password= lines"
    fi

    if (( ${#applied_secrets[@]} > 0 )); then
        log "Secrets: Applied ${applied_secrets[*]} secret(s)"
    else
        log_warn "Secrets: No Flux secrets applied; bootstrap will stall without them"
    fi
}

finalize_cluster() {
    log "Flux: Waiting for flux-system kustomization"
    until kubectl get kustomization flux-system -n flux-system >/dev/null 2>&1; do
        sleep 5
    done

    log "Flux: Triggering initial reconciliation"
    flux reconcile source git flux-system --namespace flux-system
    flux reconcile kustomization flux-system --namespace flux-system

    log "Flux: Verifying installation"
    flux check || fatal "Flux: Verification failed"

    log "Bootstrap: Complete; kubectl context is kind-${CLUSTER_NAME}"
}

# -----------------------------------------------------------------------------
# Cluster networking and lifecycle operations
# -----------------------------------------------------------------------------
configure_macvlan_network() {
    local nodes node
    local network_name="${MULTUS_NETWORK}"
    local -a attached_nodes=()
    local -a unchanged_nodes=()

    if docker network ls --format '{{.Name}}' | grep -q "^${network_name}$"; then
        log "Network: Reusing docker macvlan ${network_name}"
    else
        log "Network: Creating docker macvlan ${network_name} on ${MULTUS_PARENT_IFACE} (subnet ${MULTUS_PARENT_SUBNET}, ip-range ${MULTUS_PARENT_IP_RANGE})"
        docker network create -d macvlan --subnet "${MULTUS_PARENT_SUBNET}" --gateway "${MULTUS_PARENT_GATEWAY}" --ip-range "${MULTUS_PARENT_IP_RANGE}" -o "parent=${MULTUS_PARENT_IFACE}" "${network_name}" || fatal "Network: Failed to create macvlan ${network_name}"
    fi

    if ! nodes=$(kind get nodes --name "${CLUSTER_NAME}" 2>/dev/null); then
        log_warn "Network: No nodes reported for cluster ${CLUSTER_NAME}; skipping macvlan attachment"
        return
    fi

    while IFS= read -r node; do
        if [[ "${node}" == *"control-plane"* ]]; then
            continue
        fi

        if docker network connect "${network_name}" "${node}" 2>/dev/null; then
            attached_nodes+=("${node}")
        else
            unchanged_nodes+=("${node}")
        fi
    done <<<"${nodes}"

    if (( ${#attached_nodes[@]} > 0 )); then
        log "Network: Attached workers ${attached_nodes[*]} to ${network_name}"
    fi

    if (( ${#unchanged_nodes[@]} > 0 )); then
        log_warn "Network: Workers already on ${network_name}: ${unchanged_nodes[*]}"
    fi

    if (( ${#attached_nodes[@]} == 0 && ${#unchanged_nodes[@]} == 0 )); then
        log "Network: No worker nodes eligible for macvlan attachment"
    fi
}

create_cluster() {
    TEMP_CONFIG=$(mktemp)
    cp "${KIND_CONFIG_PATH}" "${TEMP_CONFIG}"

    if [[ -n "${BIND_ADDRESS}" ]]; then
        yq eval ".networking.apiServerAddress = \"${BIND_ADDRESS}\"" -i "${TEMP_CONFIG}"
        log "Config: Setting apiServerAddress to ${BIND_ADDRESS}"
    fi

    if [[ "$(yq eval '.nodes[0].kubeadmConfigPatches | length' "${TEMP_CONFIG}")" -eq 0 ]]; then
        fatal "Config: Kind config ${KIND_CONFIG_PATH} must define a kubeadmConfigPatch for the control plane"
    fi

    if ! cluster_exists "${CLUSTER_NAME}"; then
        log "Cluster: Creating kind cluster ${CLUSTER_NAME}"
        kind create cluster --config "${TEMP_CONFIG}" || fatal "Cluster: Failed to create kind cluster ${CLUSTER_NAME}"
    elif [[ -n "${BIND_ADDRESS}" || -n "${ADVERTISE_HOST}" ]]; then
        log_warn "Cluster: ${CLUSTER_NAME} already exists; rerun with --delete to apply updated API server exposure settings"
    fi
}

strip_kindnet_resources() {
    log "Network: Patching kindnet to remove resource requests and limits"
    if ! kubectl -n kube-system patch ds kindnet --type=json -p='[{"op":"remove","path":"/spec/template/spec/containers/0/resources"}]' >/dev/null 2>&1; then
        log_warn "Network: Failed to patch kindnet (resources may already be absent)"
    fi
}

ensure_nodes_ready() {
    log "Nodes: Waiting for all nodes to become Ready"
    kubectl wait --for=condition=Ready node --all --timeout=180s || fatal "Nodes: Failed to become Ready within timeout"
}

teardown_cluster() {
    if cluster_exists "${CLUSTER_NAME}"; then
        log "Cluster: Deleting kind cluster ${CLUSTER_NAME}"
        kind delete cluster --name "${CLUSTER_NAME}" || log_warn "Cluster: Failed to delete ${CLUSTER_NAME}"
    else
        log "Cluster: Skipping delete; cluster ${CLUSTER_NAME} not found"
    fi

    if [[ -n "${MULTUS_NETWORK}" ]]; then
        if docker network rm "${MULTUS_NETWORK}" >/dev/null 2>&1; then
            log "Network: Removed docker macvlan ${MULTUS_NETWORK}"
        else
            log "Network: Skipping removal; docker network ${MULTUS_NETWORK} not found"
        fi
    fi
}

# -----------------------------------------------------------------------------
# Environment setup and orchestration
# -----------------------------------------------------------------------------
init_environment() {
    local -a required_commands
    local cmd

    CLUSTER_NAME=$(load_cluster_name "${KIND_CONFIG_PATH}")
    DOCKER_CONTEXT="kind-${CLUSTER_NAME}"
    MULTUS_NETWORK="kind-${CLUSTER_NAME}-net"

    required_commands=(docker kind yq awk)
    if [[ "${DELETE_MODE}" != "true" ]]; then
        required_commands+=(kubectl flux helm)
    fi

    for cmd in "${required_commands[@]}"; do
        require "${cmd}"
    done

    export KUBECONFIG="${KUBECONFIG_PATH}"

    if ! docker context ls --format '{{.Name}}' 2>/dev/null | grep -qx "${DOCKER_CONTEXT}"; then
        fatal "Docker: Context '${DOCKER_CONTEXT}' not found; create it before running bootstrap"
    fi

    use_docker_context "${DOCKER_CONTEXT}"

    log "Bootstrap: Targeting cluster ${CLUSTER_NAME} (context ${DOCKER_CONTEXT})"
    log "Network: Using Multus iface=${MULTUS_PARENT_IFACE}, subnet=${MULTUS_PARENT_SUBNET}, gateway=${MULTUS_PARENT_GATEWAY}, range=${MULTUS_PARENT_IP_RANGE}"
}

bootstrap_flow() {
    log "Bootstrap: Starting create workflow for cluster ${CLUSTER_NAME}"
    detect_api_endpoint_settings
    create_cluster
    configure_macvlan_network
    patch_kubeconfig_endpoint
    ensure_nodes_ready
    strip_kindnet_resources
    setup_flux
    create_flux_secrets
    finalize_cluster
}

main() {
    trap cleanup EXIT

    parse_args "$@"
    init_environment

    if [[ "${DELETE_MODE}" == "true" ]]; then
        log "Bootstrap: Starting delete workflow for cluster ${CLUSTER_NAME}"
        teardown_cluster
        log "Bootstrap: Delete workflow complete for cluster ${CLUSTER_NAME}"
        return 0
    fi

    bootstrap_flow
}

main "$@"
