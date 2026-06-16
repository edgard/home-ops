---
# Disaster Recovery Restore Runbook

This runbook restores the homelab from GitOps state plus K8up restic repositories served by the in-cluster rest-server. The daily offsite backup of `/mnt/dpool/restic` is managed outside this repository; if TrueNAS local storage is lost, restore that directory from the offsite system before using K8up.

## Recovery Inputs

- GitHub access to this repository.
- Operator environment or `.envrc` with `TALOS_NODE`, `TALOS_CLUSTER_NAME`, `TALOS_INSTALL_DISK`, `BWS_ACCESS_TOKEN`, and Terraform backend credentials.
- `ANSIBLE_VAULT_PASSWORD` for `ansible/roles/talos/files/secrets.vault.yml`.
- Bitwarden Secrets Manager access for External Secrets and Terraform provider credentials.
- TrueNAS exports restored and reachable:
  - `/mnt/spool/appdata`
  - `/mnt/dpool/media`
  - `/mnt/dpool/restic`

## Cold Cluster Restore

1. Clone the repository and check out the desired commit.
2. Load local operator credentials.
3. Install dependencies:
   ```bash
   task deps
   ```
4. Recreate Talos, Kubernetes, and bootstrap platform services:
   ```bash
   task cluster:create
   ```
5. Reapply external infrastructure if needed:
   ```bash
   task tf:apply
   ```
6. Let Argo CD discover apps, then refresh desired state:
   ```bash
   task argo:sync
   ```
7. Confirm K8up resources are present in each protected namespace:
   ```bash
   kubectl get snapshots.k8up.io,backups.k8up.io,checks.k8up.io,prunes.k8up.io,restores.k8up.io -n selfhosted
   kubectl get snapshots.k8up.io,backups.k8up.io,checks.k8up.io,prunes.k8up.io,restores.k8up.io -n media
   kubectl get snapshots.k8up.io,backups.k8up.io,checks.k8up.io,prunes.k8up.io,restores.k8up.io -n home-automation
   ```

## App Data Restore

K8up restores are PVC-oriented. Before restoring into a live app PVC, pause Argo CD reconciliation for that app and stop every workload that can write to the target PVC. For app-template apps in this repository, the K8up snapshot path is `/data/<pvc-name>`.

1. Find the snapshot for the target PVC:
   ```bash
   kubectl get snapshots.k8up.io -n selfhosted
   kubectl get snapshot.k8up.io <snapshot-name> -n selfhosted -o yaml
   ```
2. Confirm the snapshot `spec.paths` includes the target PVC path.
3. Pause app writers:
   ```bash
   kubectl patch application <app> -n argocd --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/skip-reconcile":"true"}}}'
   kubectl scale deployment -n <namespace> -l app.kubernetes.io/instance=<app> --replicas=0
   kubectl patch cronjob -n <namespace> -l app.kubernetes.io/instance=<app> --type merge -p '{"spec":{"suspend":true}}'
   ```
4. Apply a namespace-local K8up `Restore`.

Explicit snapshot restore:

```yaml
---
apiVersion: k8up.io/v1
kind: Restore
metadata:
  name: restore-atuin
  namespace: selfhosted
spec:
  snapshot: "<snapshot-id>"
  backend:
    repoPasswordSecretRef:
      name: k8up-restic-credentials
      key: RESTIC_PASSWORD
    rest:
      url: http://restic.selfhosted.svc.cluster.local:8000/k8up/selfhosted
      userSecretRef:
        name: k8up-restic-credentials
        key: RESTIC_USERNAME
      passwordSecretReg:
        name: k8up-restic-credentials
        key: RESTIC_PASSWORD
  restoreMethod:
    folder:
      claimName: atuin
  paths:
    - /data/atuin
  delete: true
```

Date-filtered restore:

```yaml
---
apiVersion: k8up.io/v1
kind: Restore
metadata:
  name: restore-atuin-20260318
  namespace: selfhosted
spec:
  restoreTimeFilter: "2026-03-18"
  backend:
    repoPasswordSecretRef:
      name: k8up-restic-credentials
      key: RESTIC_PASSWORD
    rest:
      url: http://restic.selfhosted.svc.cluster.local:8000/k8up/selfhosted
      userSecretRef:
        name: k8up-restic-credentials
        key: RESTIC_USERNAME
      passwordSecretReg:
        name: k8up-restic-credentials
        key: RESTIC_PASSWORD
  restoreMethod:
    folder:
      claimName: atuin
  paths:
    - /data/atuin
  delete: true
```

Apply the chosen manifest:

```bash
kubectl apply -f restore.yaml
kubectl get restore.k8up.io restore-atuin -n selfhosted -o yaml
```

After the restore completes, restore workload state, remove the Argo CD pause annotation, refresh the app, wait for health, and verify expected data manually.

## Repository Layout

K8up writes namespace-scoped repositories under the existing rest-server:

- `/k8up/selfhosted`
- `/k8up/media`
- `/k8up/home-automation`

Older root restic snapshots remain emergency-only manual restore material. Supported operator restores use K8up snapshots from the namespace repositories.

## Consistency Notes

Scheduled K8up PVC backups are crash-consistent. For SQLite-heavy or critical apps, prefer app-native exports or a storage-level snapshot workflow if stronger consistency is needed later. Keep those mechanisms documented next to the app if they are added.

## Offsite Dependency

This repository does not operate or verify the daily offsite backup. If `/mnt/dpool/restic` is unavailable, complete the external offsite restore of that directory first, then confirm K8up resources before restoring apps.
