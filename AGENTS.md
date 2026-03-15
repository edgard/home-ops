# Home Ops

GitOps Talos Kubernetes homelab (single-node, local-only). Changes via PR only.
**Tech**: Talos • K8s • Argo CD • Istio Gateway API • External Secrets (Bitwarden) • Helm • Terraform

## Build & Test

- Format: `task fmt`
- Lint: `task lint` (full quality gate: behavior/integration checks, static checks, Helm render validation, and Pluto checks)
- Sync ArgoCD app: `task argo:sync [app=<name>]` (GitOps: changes must be committed and pushed to repo first)

## Developer Loop

1. Make a small change
2. If behavior changes, write or update the failing test or contract check first
3. Use `task lint` while iterating when changing script behavior or Helm/app compatibility
4. Run `task fmt`
5. Run `task lint` before commit or PR update

## Project Layout

```
apps/<category>/<app>/{app.yaml,values.yaml,manifests/}
argocd/appsets/          # Auto-discovers apps/*/*/app.yaml
bootstrap/helmfile.yaml.gotmpl  # Platform bootstrap
terraform/               # Cloudflare/Tailscale infra
```

**App Categories**:
- platform-system: cert-manager, external-dns, external-secrets, gateway-api, homelab-controller, istio, istio-base, reloader, tailscale-router
- kube-system: coredns, k8s-gateway, k8tz, multus, nfs-provisioner
- home-automation: homeassistant, scrypted
- media: bazarr, flaresolverr, plex, plextraktsync, prowlarr, qbittorrent, radarr, recyclarr, sonarr, unpackerr
- selfhosted: atuin, changedetection, echo, gatus, homepage, karakeep, paperless, renovate-operator, restic

## Conventions

### App-Template v4.6.2 Structure
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
- Gatus (service): `gatus.edgard.org/enabled: "true"`
- Homepage (route): `gethomepage.dev/{enabled,name,group,icon}`

### Networking
- HTTPRoute → `gateway.platform-system.https`, hostname: `<app>.edgard.org`
- Multus LAN IP (media apps): `k8s.v1.cni.cncf.io/networks: [{"name":"multus-lan-bridge","namespace":"kube-system","ips":["192.168.1.X/24"]}]`

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
- Lint checks: yamllint, shellcheck, tofu validate, helm render validation, appset input validation

## Architecture Overview

GitOps homelab using ArgoCD for deployment synchronization. Apps are auto-discovered from `apps/*/*/app.yaml` metadata files. Platform services bootstrap via Helmfile, infrastructure managed through Terraform (Cloudflare DNS, Tailscale networking). Single-node cluster with local-only access via Tailscale VPN.

## External Services

- Bitwarden: Secret management (`BWS_ACCESS_TOKEN` required for bootstrap and Terraform apply/plan)
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
2. For behavior changes, write the failing test first (`tests/*.bats` or a failing repo contract check)
3. Run `task lint` while iterating and before committing
4. All changes via PR only
5. Force pushes allowed only on feature branches using `--force-with-lease`
