---
# Disaster Recovery Restore Runbook

This runbook restores the homelab from GitOps state plus the local restic repository. The daily offsite backup of `/mnt/dpool/restic` is managed outside this repository; if TrueNAS local storage is lost, restore that directory from the offsite system before using the in-cluster restore commands here.

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
7. Confirm the local restic repository is reachable:
   ```bash
   task backup:snapshots
   task backup:check
   ```

## App Data Restore

Use `restore:app` for a surgical restore. The restore task pauses Argo CD reconciliation, scales Deployments to zero, suspends CronJobs for the app, restores into staging, moves the live path to `.pre-restore/`, moves staged data into place, then restores workload state.

For `restic-appdata` apps, the appdata path is derived as `<namespace>/<app>` from the app directory and rendered PVC name. Do not maintain restore paths by hand in `app.yaml`.

```bash
task restore:app app=paperless snapshot=latest confirm=RESTORE
```

For cold DR when the appdata root needs to be rebuilt, restore all `restic-appdata` apps in one operation:

```bash
task restore:all-appdata snapshot=latest confirm=RESTORE_ALL
```

Use an explicit snapshot ID for important restores:

```bash
task restore:app app=paperless snapshot=<snapshot-id> confirm=RESTORE
task restore:all-appdata snapshot=<snapshot-id> confirm=RESTORE_ALL
```

After each app restore:

1. Run `task argo:sync app=<app>`.
2. Wait for the app to become healthy.
3. Verify login and expected data manually.
4. Keep `.pre-restore/<app>-<timestamp>-<path>` until the restored app is accepted.

## Consistency Notes

The scheduled restic CronJob backs up live appdata and is crash-consistent. This repository does not provide a quiesced appdata backup command because the intended operating model is to rely on the scheduled backups, verify the repository with `task backup:check`, and prove recoverability with `task dr:drill`.

For SQLite-heavy or critical apps, prefer app-native exports or a storage-level snapshot workflow if stronger consistency is needed later. Keep those mechanisms documented next to the app if they are added.

## Offsite Dependency

This repository does not operate or verify the daily offsite backup. If `/mnt/dpool/restic` is unavailable, complete the external offsite restore of that directory first, then run `task backup:snapshots` before restoring apps.
