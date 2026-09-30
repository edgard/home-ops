# Home Ops knowledge wiki

This wiki connects the repository's configuration, policies, operational
procedures, and decision history. For a repository question, start here, follow
the relevant pages, and verify their claims against the linked current sources.
The [source catalog](sources.md) maps the broader evidence, and the
[wiki rules](AGENTS.md) describe maintenance. Current manifests and tasks
remain authoritative; verify the running system separately.

## Workflows and operations

- [Agent and contributor workflow](agent-workflow.md) — change, validation, and repository conventions.
- [Restic backup and restore runbook](operations/restic-backup-restore.md) — operator recovery procedure.
- [Wiki log](log.md) — substantial ingests and revisions.

## Architecture

- [GitOps delivery](architecture/gitops-delivery.md) — bootstrap, ApplicationSet, and reconciliation.
- [Talos and platform bootstrap](architecture/talos-bootstrap.md) — node and foundational services.
- [Networking and ingress](architecture/networking.md) — Gateway, DNS, Tailscale, and Multus.
- [Secrets and credentials](architecture/secrets.md) — Bitwarden, External Secrets, Vault, and operator inputs.
- [Storage and shared media](architecture/storage.md) — NFS appdata, media, and repository boundaries.
- [Backup and recovery](architecture/backup-recovery.md) — Restic and restore transaction.
- [Uptime monitoring](architecture/uptime.md) — Gatus targets and alerting limit.
- [Terraform](architecture/terraform.md) — Cloudflare, Tailscale, and backend.
- [Validation and PR gate](architecture/validation.md) — local checks, policy, and CI.

## Decisions

- [Shared media ownership](decisions/shared-media-group.md)
- [Gatus transition](decisions/gatus-transition.md)
- [Jellyfin cutover](decisions/jellyfin-cutover.md)
- [Talos Image Factory installer](decisions/talos-image-factory.md)
- [Restic restore transaction](decisions/restic-restore-transaction.md)
- [Validation architecture](decisions/validation-architecture.md)
- [Operator credential split](decisions/operator-credentials.md)
- [Gluetun health](decisions/gluetun-health.md)

## Applications

The app pages describe dependencies and unusual behavior. Read the linked
`app.yaml`, `values.yaml`, and manifests for current settings.

### Argo CD

- [Argo CD](apps/argocd/argocd.md)

### Home automation

- [Home Assistant](apps/home-automation/homeassistant.md)
- [Scrypted](apps/home-automation/scrypted.md)

### Kubernetes system

- [CoreDNS](apps/kube-system/coredns.md)
- [k8s-gateway](apps/kube-system/k8s-gateway.md)
- [k8tz](apps/kube-system/k8tz.md)
- [metrics-server](apps/kube-system/metrics-server.md)
- [Multus](apps/kube-system/multus.md)
- [NFS provisioner](apps/kube-system/nfs-provisioner.md)

### Media

- [Bazarr](apps/media/bazarr.md)
- [CrossWatch](apps/media/crosswatch.md)
- [FlareSolverr](apps/media/flaresolverr.md)
- [Jellyfin](apps/media/jellyfin.md)
- [MeTube](apps/media/metube.md)
- [Prowlarr](apps/media/prowlarr.md)
- [qBittorrent](apps/media/qbittorrent.md)
- [Radarr](apps/media/radarr.md)
- [Recyclarr](apps/media/recyclarr.md)
- [Sonarr](apps/media/sonarr.md)
- [Unpackerr](apps/media/unpackerr.md)

### Platform system

- [cert-manager](apps/platform-system/cert-manager.md)
- [External DNS](apps/platform-system/external-dns.md)
- [External Secrets](apps/platform-system/external-secrets.md)
- [Gateway API](apps/platform-system/gateway-api.md)
- [Gatus](apps/platform-system/gatus.md)
- [Istio](apps/platform-system/istio.md)
- [Istio base](apps/platform-system/istio-base.md)
- [Reloader](apps/platform-system/reloader.md)
- [Tailscale router](apps/platform-system/tailscale-router.md)
- [Tuppr](apps/platform-system/tuppr.md)

### Self-hosted

- [Atuin](apps/selfhosted/atuin.md)
- [Bambuddy](apps/selfhosted/bambuddy.md)
- [BentoPDF](apps/selfhosted/bentopdf.md)
- [Changedetection](apps/selfhosted/changedetection.md)
- [Echo](apps/selfhosted/echo.md)
- [Karakeep](apps/selfhosted/karakeep.md)
- [Paperless](apps/selfhosted/paperless.md)
- [Renovate Operator](apps/selfhosted/renovate-operator.md)
- [Restic](apps/selfhosted/restic.md)
- [Twitch Drops Miner](apps/selfhosted/twitch-drops-miner.md)
