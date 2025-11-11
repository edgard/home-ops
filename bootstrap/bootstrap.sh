#!/usr/bin/env bash

set -euo pipefail

# User-configurable defaults (override via environment)
readonly KUBECONFIG_PATH="${KUBECONFIG:-${HOME}/.kube/config}"
readonly MULTUS_PARENT_IFACE="${MULTUS_PARENT_IFACE:-br0}"
readonly MULTUS_PARENT_SUBNET="${MULTUS_PARENT_SUBNET:-192.168.1.0/24}"
readonly MULTUS_PARENT_GATEWAY="${MULTUS_PARENT_GATEWAY:-192.168.1.1}"
readonly MULTUS_PARENT_IP_RANGE="${MULTUS_PARENT_IP_RANGE:-192.168.1.240/29}"
readonly ARGO_HELM_VERSION="${ARGO_HELM_VERSION:-9.1.0}"

# Internal constants derived from configuration
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly KIND_CONFIG_PATH="${REPO_ROOT}/bootstrap/cluster-config.yaml"
readonly CENTRAL_SECRETS_SOPS_FILE="${REPO_ROOT}/bootstrap/central-secrets.sops.yaml"
readonly DEFAULT_SOPS_AGE_KEY_FILE="${REPO_ROOT}/.sops.agekey"
readonly CENTRAL_SECRETS_REL_PATH="${CENTRAL_SECRETS_SOPS_FILE#"${REPO_ROOT}/"}"
readonly ARGO_HELM_VALUES="${REPO_ROOT}/bootstrap/argocd-values.yaml"

# Global variables
DELETE_MODE=false
CLUSTER_NAME=""
DOCKER_CONTEXT=""
MULTUS_NETWORK=""
BIND_ADDRESS=""
ADVERTISE_HOST=""
TEMP_CONFIG=""
ARGO_HELM_SECRET_VALUES=""
ORIGINAL_CONTEXT=""
CENTRAL_SECRETS_DEC_FILE=""

# Color codes for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly NC='\033[0m'

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
            fatal "[CLI] Unknown option ${1}"
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
        fatal "[Deps] ${1} is required but not found in PATH"
    fi
}

load_cluster_name() {
    local config_path="${1}"
    local name

    if [[ ! -f "${config_path}" ]]; then
        fatal "[Config] Kind config ${config_path} does not exist"
    fi

    name=$(yq eval '.name' "${config_path}" 2>/dev/null)

    if [[ -z "${name}" || "${name}" == "null" ]]; then
        fatal "[Config] Kind config ${config_path} does not define a cluster name"
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
    [[ -n "${ARGO_HELM_SECRET_VALUES:-}" ]] && rm -f "${ARGO_HELM_SECRET_VALUES}"
    [[ -n "${CENTRAL_SECRETS_DEC_FILE:-}" ]] && rm -f "${CENTRAL_SECRETS_DEC_FILE}"
    [[ -n "${ORIGINAL_CONTEXT:-}" ]] && docker context use "${ORIGINAL_CONTEXT}" 2>/dev/null || true
}

use_docker_context() {
    local target="${1}"
    ORIGINAL_CONTEXT=$(docker context show 2>/dev/null || echo "default")

    if [[ "${ORIGINAL_CONTEXT}" != "${target}" ]]; then
        log "[Docker] Switching context to ${target}"
        docker context use "${target}"
    fi
}

load_central_secrets() {
    if [[ -n "${CENTRAL_SECRETS_DEC_FILE:-}" ]]; then
        return 0
    fi

    if [[ ! -f "${CENTRAL_SECRETS_SOPS_FILE}" ]]; then
        return 1
    fi

    require sops
    local key_file="${SOPS_AGE_KEY_FILE:-}"
    if [[ -z "${key_file}" && -f "${DEFAULT_SOPS_AGE_KEY_FILE}" ]]; then
        key_file="${DEFAULT_SOPS_AGE_KEY_FILE}"
    fi

    CENTRAL_SECRETS_DEC_FILE=$(mktemp)

    if [[ -n "${key_file}" ]]; then
        if ! SOPS_AGE_KEY_FILE="${key_file}" sops --decrypt "${CENTRAL_SECRETS_SOPS_FILE}" >"${CENTRAL_SECRETS_DEC_FILE}"; then
            fatal "[Secrets] Failed to decrypt ${CENTRAL_SECRETS_REL_PATH}"
        fi
    else
        if ! sops --decrypt "${CENTRAL_SECRETS_SOPS_FILE}" >"${CENTRAL_SECRETS_DEC_FILE}"; then
            fatal "[Secrets] Failed to decrypt ${CENTRAL_SECRETS_REL_PATH}"
        fi
    fi

    return 0
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
        log "[API] Exposing control plane on ${remote_host} (bind ${BIND_ADDRESS})"
    else
        log "[API] Using local control plane endpoint"
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
                log "[Kubeconfig] Patching server endpoint to https://${ADVERTISE_HOST}:${port}"
                kubectl config set-cluster "${cluster_context}" "--server=https://${ADVERTISE_HOST}:${port}"
            fi
        fi
    fi
}

# -----------------------------------------------------------------------------
# Argo CD deployment helpers
# -----------------------------------------------------------------------------
ensure_argocd_admin_password_override() {
    if ! ensure_central_secrets "Argo admin password"; then
        fatal "[Argo] Central secrets are required to set the admin password"
    fi

    local admin_hash
    admin_hash=$(yq -r '.stringData.argocd_admin_password // ""' "${CENTRAL_SECRETS_DEC_FILE}")
    if [[ -z "${admin_hash}" || "${admin_hash}" == "null" ]]; then
        fatal "[Argo] argocd_admin_password is required inside ${CENTRAL_SECRETS_REL_PATH} (decrypted)"
    fi

    ARGO_HELM_SECRET_VALUES=$(mktemp)
    HASH="${admin_hash}" yq -n '.configs.secret.argocdServerAdminPassword = env(HASH)' >"${ARGO_HELM_SECRET_VALUES}"

    log "[Argo] Using admin password from ${CENTRAL_SECRETS_REL_PATH} (decrypted)"
}

deploy_argocd() {
    log "[Argo] Installing via Helm chart argo-cd@${ARGO_HELM_VERSION}"
    helm repo add argo "https://argoproj.github.io/argo-helm" --force-update >/dev/null 2>&1 || true
    local -a values_args=("-f" "${ARGO_HELM_VALUES}")
    if [[ -n "${ARGO_HELM_SECRET_VALUES:-}" ]]; then
        values_args+=("-f" "${ARGO_HELM_SECRET_VALUES}")
    fi

    helm upgrade --install "argocd" argo/"argo-cd" \
        --namespace argocd \
        --create-namespace \
        --version "${ARGO_HELM_VERSION}" \
        "${values_args[@]}" \
        --wait || fatal "[Argo] Helm install failed"
    log "[Argo] Helm install completed"
}

ensure_central_secrets() {
    local subject="${1:-Central secrets}"

    if load_central_secrets; then
        return 0
    fi

    log_warn "[Secrets] ${subject} skipped because ${CENTRAL_SECRETS_REL_PATH} is missing"
    return 1
}

apply_central_secrets() {
    if ! ensure_central_secrets "Central secret manifest"; then
        return
    fi

    local display="${CENTRAL_SECRETS_REL_PATH} (decrypted)"
    log "[Secrets] Applying ${display}"
    kubectl apply -f "${CENTRAL_SECRETS_DEC_FILE}" || fatal "[Secrets] Failed to apply ${display}"
}

apply_git_repo_secret() {
    if ! ensure_central_secrets "Homelab-git secret"; then
        return
    fi

    local repo_fields=()
    mapfile -t repo_fields < <(yq -r '[
        .stringData.argocd_repo_url // "",
        .stringData.argocd_repo_username // "",
        .stringData.argocd_repo_password // ""
    ] | .[]' "${CENTRAL_SECRETS_DEC_FILE}")

    local repo_url="${repo_fields[0]:-}"
    local repo_username="${repo_fields[1]:-}"
    local repo_password="${repo_fields[2]:-}"

    if [[ -z "${repo_url}" || -z "${repo_username}" || -z "${repo_password}" ]]; then
        log_warn "[Secrets] Required argocd_repo_* keys missing in ${CENTRAL_SECRETS_REL_PATH} (decrypted); skipping homelab-git secret"
        return
    fi

    log "[Secrets] Applying argocd/homelab-git from ${CENTRAL_SECRETS_REL_PATH} (decrypted)"
    kubectl -n argocd create secret generic homelab-git \
        --type Opaque \
        --from-literal=url="${repo_url}" \
        --from-literal=username="${repo_username}" \
        --from-literal=password="${repo_password}" \
        --dry-run=client -o yaml \
        | yq eval '.metadata.labels."argocd.argoproj.io/secret-type" = "repository"' - \
        | kubectl apply -f - || fatal "[Secrets] Failed to apply argocd/homelab-git"
}

apply_root_application() {
    local root_app="${REPO_ROOT}/kubernetes/clusters/homelab/root-application.yaml"
    log "[Argo] Applying homelab root application"
    kubectl apply -f "${root_app}" || fatal "[Argo] Failed to apply root application"
}

wait_for_root_application() {
    local app_name="homelab-root"
    local namespace="argocd"
    local attempts=30

    log "[Argo] Waiting for ${app_name} to sync"
    for ((i = 0; i < attempts; i++)); do
        local status
        status=$(kubectl -n "${namespace}" get application "${app_name}" -o jsonpath='{.status.sync.status} {.status.health.status}' 2>/dev/null || true)
        if [[ "${status}" == "Synced Healthy" ]]; then
            log "[Argo] ${app_name} is synced and healthy"
            return
        fi
        sleep 10
    done

    log_warn "[Argo] ${app_name} did not report Synced/Healthy within the timeout; inspect with 'kubectl -n argocd get app ${app_name} -o yaml'"
}

finalize_cluster() {
    log "[Bootstrap] Complete; kubectl context is kind-${CLUSTER_NAME}"
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
        log "[Network] Reusing Docker macvlan ${network_name}"
    else
        log "[Network] Creating Docker macvlan ${network_name} on ${MULTUS_PARENT_IFACE} (subnet ${MULTUS_PARENT_SUBNET}, ip-range ${MULTUS_PARENT_IP_RANGE})"
        docker network create -d macvlan --subnet "${MULTUS_PARENT_SUBNET}" --gateway "${MULTUS_PARENT_GATEWAY}" --ip-range "${MULTUS_PARENT_IP_RANGE}" -o "parent=${MULTUS_PARENT_IFACE}" "${network_name}" || fatal "[Network] Failed to create macvlan ${network_name}"
    fi

    if ! nodes=$(kind get nodes --name "${CLUSTER_NAME}" 2>/dev/null); then
        log_warn "[Network] No nodes reported for cluster ${CLUSTER_NAME}; skipping macvlan attachment"
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
        log "[Network] Attached workers ${attached_nodes[*]} to ${network_name}"
    fi

    if (( ${#unchanged_nodes[@]} > 0 )); then
        log_warn "[Network] Workers already attached to ${network_name}: ${unchanged_nodes[*]}"
    fi

    if (( ${#attached_nodes[@]} == 0 && ${#unchanged_nodes[@]} == 0 )); then
        log "[Network] No worker nodes eligible for macvlan attachment"
    fi
}

create_cluster() {
    TEMP_CONFIG=$(mktemp)
    cp "${KIND_CONFIG_PATH}" "${TEMP_CONFIG}"

    if [[ -n "${BIND_ADDRESS}" ]]; then
        yq eval ".networking.apiServerAddress = \"${BIND_ADDRESS}\"" -i "${TEMP_CONFIG}"
        log "[Config] Setting Kind apiServerAddress override to ${BIND_ADDRESS}"
    fi

    if [[ "$(yq eval '.nodes[0].kubeadmConfigPatches | length' "${TEMP_CONFIG}")" -eq 0 ]]; then
        fatal "[Config] Kind config ${KIND_CONFIG_PATH} must define a kubeadmConfigPatch for the control plane"
    fi

    if ! cluster_exists "${CLUSTER_NAME}"; then
        log "[Cluster] Creating Kind cluster ${CLUSTER_NAME}"
        kind create cluster --config "${TEMP_CONFIG}" || fatal "[Cluster] Failed to create Kind cluster ${CLUSTER_NAME}"
    elif [[ -n "${BIND_ADDRESS}" || -n "${ADVERTISE_HOST}" ]]; then
        log_warn "[Cluster] ${CLUSTER_NAME} already exists; rerun with --delete to apply updated API server exposure settings"
    fi
}

strip_kindnet_resources() {
    log "[Network] Patching Kindnet to remove resource requests and limits"
    if ! kubectl -n kube-system patch ds kindnet --type=json -p='[{"op":"remove","path":"/spec/template/spec/containers/0/resources"}]' >/dev/null 2>&1; then
        log_warn "[Network] Failed to patch Kindnet (resources may already be absent)"
    fi
}

ensure_nodes_ready() {
    log "[Nodes] Waiting for all nodes to become Ready"
    kubectl wait --for=condition=Ready node --all --timeout=180s || fatal "[Nodes] Failed to become Ready within timeout"
    log "[Nodes] All nodes are Ready"
}

teardown_cluster() {
    if cluster_exists "${CLUSTER_NAME}"; then
        log "[Cluster] Deleting Kind cluster ${CLUSTER_NAME}"
        kind delete cluster --name "${CLUSTER_NAME}" || log_warn "[Cluster] Failed to delete ${CLUSTER_NAME}"
    else
        log "[Cluster] Skipping delete; cluster ${CLUSTER_NAME} not found"
    fi

    if [[ -n "${MULTUS_NETWORK}" ]]; then
        if docker network rm "${MULTUS_NETWORK}" >/dev/null 2>&1; then
            log "[Network] Removed Docker macvlan ${MULTUS_NETWORK}"
        else
            log "[Network] Skipping removal; Docker network ${MULTUS_NETWORK} not found"
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
        required_commands+=(kubectl helm)
    fi

    for cmd in "${required_commands[@]}"; do
        require "${cmd}"
    done

    export KUBECONFIG="${KUBECONFIG_PATH}"

    if ! docker context ls --format '{{.Name}}' 2>/dev/null | grep -qx "${DOCKER_CONTEXT}"; then
        fatal "[Docker] Context '${DOCKER_CONTEXT}' not found; create it before running bootstrap"
    fi

    use_docker_context "${DOCKER_CONTEXT}"

    log "[Bootstrap] Targeting cluster ${CLUSTER_NAME} (context ${DOCKER_CONTEXT})"
    log "[Network] Using Multus iface=${MULTUS_PARENT_IFACE}, subnet=${MULTUS_PARENT_SUBNET}, gateway=${MULTUS_PARENT_GATEWAY}, range=${MULTUS_PARENT_IP_RANGE}"
}

bootstrap_flow() {
    log "[Bootstrap] Starting create workflow for cluster ${CLUSTER_NAME}"
    detect_api_endpoint_settings
    create_cluster
    configure_macvlan_network
    patch_kubeconfig_endpoint
    ensure_nodes_ready
    strip_kindnet_resources
    apply_central_secrets
    ensure_argocd_admin_password_override
    deploy_argocd
    apply_git_repo_secret
    apply_root_application
    wait_for_root_application
    finalize_cluster
}

main() {
    trap cleanup EXIT

    parse_args "$@"
    init_environment

    if [[ "${DELETE_MODE}" == "true" ]]; then
        log "[Bootstrap] Starting delete workflow for cluster ${CLUSTER_NAME}"
        teardown_cluster
        log "[Bootstrap] Delete workflow complete for cluster ${CLUSTER_NAME}"
        return 0
    fi

    bootstrap_flow
}

main "$@"
