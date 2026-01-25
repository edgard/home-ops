# AI Agent Instructions
<!-- Keep under 100 lines. Be concise. -->
## Project Overview
GitOps Talos Kubernetes homelab (single-node, local-only). Changes via PR only.
**Tech**: Talos • K8s • Argo CD • Istio Gateway API • External Secrets (Bitwarden) • Helm • Terraform

## Quick Reference
`task fmt` | `task lint` (requires BWS_ACCESS_TOKEN, AWS creds) | `task cluster:create` | `task argo:sync [app=<name>]`

## Directory Structure
```
apps/<category>/<app>/{config.yaml,values.yaml,manifests/}
argocd/appsets/          # Auto-discovers apps/*/config.yaml
bootstrap/helmfile.yaml.gotmpl  # Platform bootstrap
terraform/               # Cloudflare/Tailscale infra
```

## App Categories
platform-system: cert-manager, external-dns, external-secrets, gateway-api, homelab-controller, istio, tailscale-operator
kube-system: coredns, k8s-gateway, k8tz, multus, nfs-provisioner
home-automation: homebridge, matterbridge, mosquitto, scrypted, zigbee2mqtt
media: bazarr, flaresolverr, plex, plextraktsync, prowlarr, qbittorrent, radarr, recyclarr, sonarr, unpackerr
selfhosted: atuin, changedetection, echo, gatus, homepage, karakeep, n8n, paperless, restic

## App-Template v4.6.2 Structure
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
# s6-overlay: run as root + SETUID/SETGID; <1024 ports: +NET_BIND_SERVICE
```

## Common Annotations
Reloader: `reloader.stakater.com/auto: "true"` (controllers)
Gatus: `gatus.edgard.org/enabled: "true"` (service)
Homepage: `gethomepage.dev/{enabled,name,group,icon}` (route)

## Networking
HTTPRoute → `gateway.platform-system.https`, hostname: `<app>.edgard.org`
Multus LAN IP (media apps): `k8s.v1.cni.cncf.io/networks: [{"name":"multus-lan-bridge","namespace":"kube-system","ips":["192.168.1.X/24"]}]`

## Storage
`nfs-fast`: `/mnt/spool/appdata` (default); `nfs-media`: `/mnt/dpool/media` (use `existingClaim: media`); `nfs-restic`: `/mnt/dpool/restic`

## ArgoCD Sync Waves
`-4` CRDs → `-3` Controllers/DNS → `-2` Mesh/PVCs → `-1` k8tz → `0` Apps

## ExternalSecret Pattern
`refreshInterval → secretStoreRef (name, kind) → target → data`; Store: `external-secrets-store`

## Resource Naming
Manifest: `{app}-{descriptor}.{kind}.yaml`; ExternalSecret: `{app}-[{descriptor}-]credentials`; HTTPRoute: `{app}`; PVC: `{app}-{suffix}` or `existingClaim: media`

## Code Standards
YAML: 2 spaces, `---` on line 1; Fields: `apiVersion → kind → metadata → spec`; Metadata: `name → namespace → labels → annotations`
Pre-commit: yamllint, shellcheck, tofu-validate, helm-lint

## Environment Variables
`BWS_ACCESS_TOKEN` (Bitwarden: bootstrap, lint, tf); `AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY` (TF S3 backend); `TALOS_NODE/CLUSTER_NAME/INSTALL_DISK` (Talos)

## Constraints
Local + Tailscale only (192.168.1.0/24); Single-node → `replicas: 1`, `strategy: Recreate`; Never commit directly to master
