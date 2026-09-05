# Home Ops

GitOps Talos Kubernetes homelab (single-node, local-only). Changes via PR only.
**Tech**: Talos • K8s • Argo CD • Istio Gateway API • External Secrets (Bitwarden) •
VictoriaMetrics/VictoriaLogs/VLAgent/Grafana • Helm • Ansible • Terraform

## Build & Test

- Format: `task fmt`
- Format check: `task fmt:check`
- Dependencies: `task deps` creates `.venv` and installs Ansible Python dependencies
- Lint: `task lint` (offline validation: formatting, shellcheck, yamllint, GitHub Actions workflow lint, Ansible syntax/lint/contracts, metadata policy, raw manifest policy/schema/deprecation checks, batched rendered policy/schema/deprecation checks, `tofu validate`)
- Focused checks: `task lint:static`, `task lint:workflows`, `task lint:ansible`, `task lint:kubernetes`, `task lint:terraform`
- Policy layers:
  - `policy/metadata/` validates app metadata structure and required sync waves
  - `policy/kubernetes/` validates manifest and rendered-workload guardrails
- Policy semantics are regression-tested in `policy/metadata/*_test.rego` and `policy/kubernetes/*_test.rego`
- CI gate: GitHub `Quality Gate` job, backed by the same focused local `task lint:*` targets aggregated by `task lint`
- Pre-commit gate: `task precommit` (`task fmt` + `task lint`)
- Sync ArgoCD app: `task argo:sync [app=<name>]` (GitOps: changes must be committed and pushed to repo first)

## Developer Loop

1. Make a small change
2. If behavior changes, write or update the failing policy or contract check first
3. Use `task lint` while iterating when changing script behavior or Helm/app compatibility
4. Run `task fmt`
5. Run `task lint` before commit or PR update

## Project Layout

```
apps/<category>/<app>/{app.yaml,values.yaml,manifests/}
argocd/appsets/          # Auto-discovers apps/*/*/app.yaml
ansible/                 # Local orchestration, inventory, roles, role defaults, and Talos bootstrap inputs
terraform/               # Cloudflare/Tailscale infra
```

**App Categories**:
- platform-system: cert-manager, external-dns, external-secrets, gateway-api, istio, istio-base, prometheus-blackbox-exporter, reloader, tailscale-router, victoria-logs-collector, victoria-logs-single, victoria-metrics-k8s-stack
- kube-system: coredns, k8s-gateway, k8tz, multus, nfs-provisioner
- home-automation: homeassistant, scrypted
- media: bazarr, flaresolverr, plex, plextraktsync, prowlarr, qbittorrent, radarr, recyclarr, sonarr, unpackerr
- selfhosted: atuin, changedetection, echo, karakeep, paperless, renovate-operator, restic

## Conventions

### App-Template v5 Structure
Order: `defaultPodOptions → controllers → service → route → persistence → configMaps`

```yaml
defaultPodOptions:
  securityContext:
    fsGroup: 1000
    fsGroupChangePolicy: OnRootMismatch
    runAsGroup: 1000
    runAsNonRoot: true
    runAsUser: 1000
controllers:
  main:
    annotations:
      reloader.stakater.com/auto: "true"
    replicas: 1
    strategy: Recreate
    containers:
      app:
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop: [ALL]
```

### Common Annotations
- Reloader (controllers): `reloader.stakater.com/auto: "true"`

### Networking
- HTTPRoute → `gateway.platform-system.https`, hostname: `<app>.edgard.org`
- Multus LAN IP (media apps): `k8s.v1.cni.cncf.io/networks: [{"name":"multus-lan-bridge","namespace":"kube-system","ips":["192.168.1.X/24"]}]`

### Monitoring
- `victoria-metrics-k8s-stack` is the compact monitoring stack: VictoriaMetrics
  Operator, VMAgent, VMSingle, kube-state-metrics, node-exporter, and Grafana.
- VMSingle retains metrics for 30 days on a 50Gi `nfs-fast` claim. VMAgent is the
  only metrics scraper. VMAlert, VMAlertmanager, standalone Alertmanager,
  Prometheus compatibility conversion, and Prometheus Operator CRDs are disabled.
- The chart's complete operator CRD bundle is disabled. Twelve CRD schemas are
  vendored from `victoria-metrics-operator` 0.67.2: six active APIs plus six
  indexer-only schemas required for operator v0.74.0 startup. Policy forbids
  resources for every indexer-only schema, and the corresponding controllers are
  disabled; VMAlert and VMAlertmanager CRDs remain absent.
- Grafana is the operations UI at `grafana.edgard.org`; Homepage and Gatus are
  intentionally not part of the stack.
- Grafana Unified Alerting is the sole alert-rule and notification engine. Exactly
  20 actionable alert rules are file-provisioned from Git and read-only in the UI;
  there are no recording rules. Its built-in notification router sends Telegram
  messages using Bitwarden-backed `telegram_bot_token` and `telegram_chat_id`;
  there is no separate Alertmanager.
- Grafana exposes exactly five dashboards: Home Ops Overview, Node Exporter Full,
  VictoriaMetrics Single, VictoriaLogs Single, and Pod Logs Explorer. The three
  vendor dashboards are synchronized by the pinned stack chart; the two Home Ops
  dashboards are stored in Git and query raw metrics or logs.
- Blackbox Exporter replaces Gatus-style route, DNS, and connectivity checks
  with `operator.victoriametrics.com/v1beta1` `VMProbe` resources.
- Use `VMServiceScrape` or `VMPodScrape` for in-cluster metrics endpoints. Use
  `VMProbe` for user-facing HTTPRoute checks, DNS checks, ICMP, and other
  blackbox reachability tests.
- Do not add `gethomepage.dev/*` or `gatus.home-operations.com/endpoint`
  annotations to routed apps.
- VictoriaLogs is a single StatefulSet with 30-day retention on a retained 30Gi
  `nfs-fast` claim. It is internal-only and has no HTTPRoute.
- VLAgent is a confined-root DaemonSet that reads pod stdout/stderr through
  read-only `/var/log` and `/var/lib` host mounts. Its only writable path is the
  dedicated node-local `/var/lib/vl-collector` queue. Kubernetes Events are not
  collected.
- Log stream fields are `cluster`, `kubernetes.pod_namespace`,
  `kubernetes.pod_labels.app.kubernetes.io/name`, and
  `kubernetes.container_name`. Pod, node, image, runtime, and other Kubernetes
  metadata remain ordinary searchable fields.
- Grafana provisions VictoriaLogs as a non-editable internal datasource with UID
  `victorialogs`. Anonymous Viewer access means reachable LAN/Tailscale users can
  query collected logs.
- VMSingle, VictoriaLogs, and Grafana data are included in Restic backup and
  restore. VLAgent's node-local buffer is transient and excluded from restore.
- Talos host-service logs, external Victoria endpoints, log-derived alerts, and
  object storage are out of scope.

### Storage
- `nfs-fast`: `/mnt/spool/appdata` (default)
- `nfs-media`: `/mnt/dpool/media` (use `existingClaim: media`)
- `nfs-restic`: `/mnt/dpool/restic`

### ArgoCD Sync Waves
`-4` CRDs → `-3` Controllers/DNS → `-2` Mesh/PVCs → `-1` k8tz → `0` Apps

### ExternalSecret Pattern
`refreshInterval → secretStoreRef (name, kind) → target → data`
Store: `external-secrets-store`

### Resource Naming
- Manifest: `{app}-{descriptor}.{kind}.yaml`
- ExternalSecret: `{app}-[{descriptor}-]credentials`
- HTTPRoute: `{app}`
- PVC: `{app}-{suffix}` or `existingClaim: media`

### Code Standards
- YAML: 2 spaces, `---` on line 1
- Field order: `apiVersion → kind → metadata → spec`
- Metadata order: `name → namespace → labels → annotations`
- Validation split:
  - `task lint` covers direct repo validation and aggregates the focused `lint:*` targets
  - CI runs the focused targets as separate pull-request jobs and uses `Quality Gate` as the required aggregate check
  - Prefer policy or lint checks when the assertion is about repository content
- Metadata policy lives under `policy/metadata/` and is enforced via Conftest
- Kubernetes policy lives under `policy/kubernetes/` and is enforced against raw manifests and rendered app output
- `sync.wave` is required in every `apps/*/*/app.yaml` and must stay within the repo wave bands `-4` to `0`
- Kubernetes target version comes from `apps/platform-system/tuppr/manifests/tuppr-kubernetes.kubernetesupgrade.yaml`
- Validation script:
  - `scripts/validate-kubernetes.sh` runs source, metadata, raw manifest, rendered manifest, schema, and deprecation checks
  - `scripts/validate-kubernetes.sh` resolves the Kubernetes target version from Tuppr, builds the Conftest metadata inventory, caches chart pulls for the current validation run, and batches rendered output into a temp tree so policy, schema, and deprecation checks each run once across the rendered set
- Ansible roles:
  - Role-owned defaults live in `ansible/roles/*/defaults/main.yml`; inventory vars stay limited to local/site inputs.
  - Kubernetes operations use `kubernetes.core` modules with `kube_context`; avoid adding `kubectl` tasks.
  - Local runtime credentials (`BWS_ACCESS_TOKEN`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) come from git-ignored `.envrc` or the operator environment.
  - Talos bootstrap secrets live in committed Ansible Vault file `ansible/roles/talos/files/secrets.vault.yml`.
  - Legacy plaintext Talos secrets at `ansible/roles/talos/files/secrets.yaml` remain git-ignored and must not be reintroduced.

## Architecture Overview

GitOps homelab using ArgoCD for deployment synchronization. Apps are auto-discovered from `apps/*/*/app.yaml` metadata files. Platform services bootstrap via Ansible-managed Helm installs that read the same app metadata, infrastructure is managed through Terraform (Cloudflare DNS, Tailscale networking). Single-node cluster with local-only access via Tailscale VPN.

## External Services

- Bitwarden: Secret management (`BWS_ACCESS_TOKEN` required for bootstrap and Terraform plan/apply)
- AWS S3: Terraform backend storage (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
- Cloudflare: DNS management
- Tailscale: VPN networking (192.168.1.0/24)

## Gotchas

- Local + Tailscale only (192.168.1.0/24)
- Single-node → `replicas: 1`, `strategy: Recreate`
- s6-overlay: run as root + SETUID/SETGID; ports <1024: +NET_BIND_SERVICE
- Never commit directly to `master`

## Git Workflow

1. Branch from `master` with descriptive name
2. For behavior changes, write the failing policy or repo contract check first
3. Run `task lint` before committing
4. All changes via PR only
5. Force pushes allowed only on feature branches using `--force-with-lease`
