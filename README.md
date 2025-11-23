# Home Ops

Kubernetes homelab repo managed by Argo CD and bootstrapped with Kind. Manifests and Helm values live here so the cluster state is reproducible from source.

## Quick Start
- Install: `python3`, `kind`, `kubectl`, `sops`, `age-keygen`, `prettier`, `yamlfmt`, `yamllint`.
- Generate an Age key (kept local): `make secrets-create-key`.
- Create/edit encrypted secrets: `make secrets-edit` (writes `cluster/config/cluster-secrets.sops.yaml`).
- Bootstrap remote/target cluster: `make bootstrap` (uses `scripts/bootstrap.py`, installs Argo CD, syncs apps).
- Remove cluster: `make bootstrap-delete`; rebuild: `make bootstrap-recreate`.

## Local Testing
- Bring up a local Kind cluster with repo config: `make kind-create`; tear down with `make kind-delete`.
- Apply decrypted secrets to the active cluster: `make secrets-apply`.
- Check nodes/services: `kubectl get nodes -o wide`, `kubectl get pods -A`.
- Force Argo CD resync (optionally scoped): `make argo-sync ARGOCD_SELECTOR=key=value`.

## Linting & Formatting
- Run `make lint` to format YAML with Prettier + yamlfmt and lint with yamllint.
- Keep YAML 2-space indented and align filenames with the chart/app they configure.

## Layout
- `cluster/config/`: Kind cluster config plus SOPS-encrypted secrets and template.
- `kubernetes/argocd/`: Argo CD bootstrap and Application definitions.
- `kubernetes/apps/`: App groups (edge-services, platform-system, ops, media, home-automation, arc, argocd) with Helm values/manifests.
- `scripts/bootstrap.py`: Cluster bootstrap automation.
- `Makefile`: Tasks for bootstrap, Kind management, secrets, linting, Argo sync.

## Contributing
- Use Conventional Commits (e.g., `refactor(argo): ...`, `chore(deps): ...`).
- Do not commit decrypted secrets or `.sops.agekey`.
- In PRs include what changed, validation steps (lint, Kind/Argo checks), and any manual follow-ups.
