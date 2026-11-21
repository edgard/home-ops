# Kubernetes Restic restore runbook

Purpose: recover existing Kubernetes appdata and verify the independent copy of the shared Restic repository.
Status: current. Reviewed against: `d80872c8700249ef67aa42919e297c37e75faef3` plus the bare-metal migration changes in this revision.

## Repository and backups

The server uses the retained local `selfhosted/restic-repo` claim at
`/var/mnt/dpool/restic`. Its startup checks the pool verification marker for
the current boot, the mounted ZFS filesystem `dpool/restic`, the original
`.htpasswd`, and the decrypted repository ID. Supply the existing
`restic_server_password` and `restic_repository_id` from Bitwarden. Keep the
original repository, HTTP credentials and workstation endpoint during recovery.

Kubernetes clients use `rest:http://restic.selfhosted.svc.cluster.local:8000/`.
The workstation endpoint is `rest:http://restic.edgard.org:8000/`. Inspect the
actual workstation snapshot families and pins in that same repository before
cutover. Only the Kubernetes maintenance job performs retention.

After Argo handoff the three namespace backup CronJobs are scheduled daily.
Each mounts its enumerated appdata claims read-only, verifies source mounts and
repository identity, and backs up `/data/appdata/<namespace>` with host
`homelab` and tag `appdata`. Claim directories within both these snapshots and
older aggregate snapshots use `/data/appdata/<namespace>/<actual-pvc-name>`.
Shared media is outside this backup. When adding a persistent application,
add its actual claim to the namespace job and verify a snapshot containing it.
These backups read live files. Use native application backups or a
writer-quiesced copy for database-consistent recovery points.

## Offsite copy and retention

Keep the established B2 bucket, prefix, encryption password/salt, and crypt
settings in the scoped Bitwarden item `restic_b2_rclone_config`. The supplied
rclone configuration must define the `restic-cloud` crypt remote with
`filename_encryption = off` over the existing B2 destination. Preserve
independent access to these settings and the Restic password for disaster
recovery. The home-automation reader can fetch only
`selfhosted/restic-credentials`.

Before enabling the scheduled copy, use a trusted machine and independent copy
of that configuration to open the B2 repository read-only. For example, set
`RCLONE_CONFIG` to the private configuration file and `RESTIC_PASSWORD_FILE`
to the private repository password file. Supply the expected repository ID
from the cutover record. Check a known application snapshot and a workstation
snapshot and restore a representative file from each into private scratch
storage. Compare contents to previously recorded hashes.

```sh
export RESTIC_REPOSITORY=rclone:restic-cloud:
restic --no-lock cat config
restic --no-lock snapshots
restic --no-lock restore "$SNAPSHOT_ID" --target "$PRIVATE_SCRATCH" --include "$KNOWN_FILE" --verify
```

After a successful drill, set `SNAPSHOT_ID` to one full 64-character ID just
verified from B2. Enable copying once in the recovered cluster.

```sh
kubectl -n selfhosted create configmap restic-cloud-approval --from-literal=snapshot-id="$SNAPSHOT_ID"
```

The maintenance CronJob requires that marker, verifies the existing encrypted
destination config byte-for-byte against the local repository, and checks the
approved remote snapshot object's SHA-256 before writing. It copies packs and
indexes before publishing the snapshot IDs present at the start of the copy.
It skips locks and performs no remote deletion. The remote accumulates retired
objects and old snapshot IDs, so monitor B2 storage independently. Repository
maintenance runs the weekly local retention and integrity checks after a
successful copy. Missing approval or a failed check stops both operations.
Inspect the CronJob's most recent Job and perform periodic independent restore
drills. The schedules and retention counts live in the namespace values
linked below.

## Restore one application

Use these commands with a running cluster, existing bound claims, the
verified repository server and their owning Argo Applications. The default
preview and Ansible check mode read snapshot metadata. `latest` resolves the
newest matching aggregate or namespace snapshot per application namespace.
The plan displays the full snapshot ID, namespace, claim, destination dataset
and workload replica counts. Confirm with that exact ID to reproduce a preview.

```sh
task restic:restore app=paperless
task restic:restore app=paperless snapshot="$SNAPSHOT_ID" confirm_restore=true
```

The transaction acquires the exclusive `selfhosted/restic-restore-lock`,
pauses cluster-wide Argo application reconciliation, suspends relevant CronJobs
and waits for their existing Jobs to drain. It scales down selected application
writers and requires their claims to have no active Pod consumers. A Job in
each application's namespace checks the actual ZFS dataset and mounts the
bound claims at `/restore/<claim>`. Restic restores only the explicitly pinned
subtree, removes extra destination files, and verifies restored content.
Legacy aggregate snapshots use the existing xattr exclusion. New native-ZFS
snapshots restore their supported metadata. Successful completion returns
workloads, CronJobs and the controller to their captured configuration.

If execution stops, inspect the restore Job and the lock's
`plan.json`, `cronjobs.json`, and `controller-replicas` entries.
Inspect recovery data before restarting writers. The lock prevents concurrent
or accidental reruns. After manually finishing or rolling back that transaction,
return the recorded settings, remove its inspected Job and then remove the
lock. Keep a copy of the recovery record until application checks pass.

## Restore all appdata

```sh
task restic:restore-all
task restic:restore-all confirm_restore=true
```

An explicit historical aggregate snapshot can cover all namespaces. To pin
different modern snapshots in one transaction, pass a namespace-to-full-ID
mapping as the Ansible extra variable `restic_restore_snapshot`. A modern
snapshot from one namespace cannot restore another namespace. Restore-all
selects Argo-owned, bound `zfs-appdata` claims. Media, repository storage
and SparkyFitness have their own recovery procedures.

## SparkyFitness database and files

SparkyFitness's native full archives contain a compressed SQL dump and an uploads
archive. Restic excludes the live PostgreSQL subdirectory. Restoring its PVC as
files therefore does not restore the database. For a running installation, recover
the selected completed archive into a temporary directory and use the native
administrator restore page, retaining the same Bitwarden encryption/auth secrets.

For cold recovery, use this manual application-specific sequence:

1. Recover the selected completed archive from Restic into temporary storage.
   Preserve the current data if it is still needed; do not overwrite an existing
   installation before confirming the selected archive.
2. Hold Argo reconciliation for this app using the existing maintenance procedure.
   Stop the frontend and backend; start only its dedicated PostgreSQL.
3. Use a temporary official PostgreSQL 18 client mounting the app PVC at `/data`
   and the existing app Secret for its owner credentials. Extract the outer
   archive and create the `sparky_app` LOGIN role if it is missing, leaving its
   password unset until the backend provisions it. Native dumps include grants
   to this role but do not create it. Drop/recreate only `sparkyfitness_db`, then stream the inner
   `sparkyfitness_db_backup_*.sql.gz` into `psql --set ON_ERROR_STOP=1` against that
   database. Do not use `pg_restore`: this native archive contains plain SQL.
4. Replace `/data/uploads` with the recovered uploads archive contents, preserving
   the backend's writable UID/group. Retain the API-encryption and authentication
   keys from Bitwarden. Leave the PostgreSQL files to PostgreSQL itself.
5. Remove the temporary client, resume the backend and then the frontend, and
   restore the recorded Argo settings. The backend maintains its runtime role.
   Verify login, records, upload hashes, decrypted AI/provider settings and backup
   scheduling before allowing new imports. Clean temporary recovery files.

The app's dedicated PostgreSQL owner retains the upstream privileges needed by
native restore. Native restore loads a staging database and swaps it into place,
retaining the previous database and uploads for recovery. Verify SQL results,
records, and uploads after the swap before removing the retained copies.
See the [app page](../apps/selfhosted/sparkyfitness.md) and
[backup implementation](https://github.com/CodeWithCJ/SparkyFitness/blob/v1.12.1/SparkyFitnessServer/services/backupService.ts).

The generic role excludes both the SparkyFitness app and its data claim,
including during restore-all.

## Fresh cluster or missing storage

Use the [bare-metal migration and recovery procedure](truenas-migration.md)
for a fresh control plane. Keep writers and Argo handoff withheld until
the actual `dpool` GUID, boot-time mount identities, retained repository,
and expected data have been verified. Recover the original Kubernetes/Talos
identity and etcd/PV metadata where available. For an intentional rebuild
with new claim identities, use the pre-handoff restore into freshly
provisioned claims and verify the data. The ordinary restore role requires
already-owned, bound claims and an active Argo application controller.

### Retained ZFS data after loss of etcd

While the cluster is healthy, keep a current etcd snapshot and a binding map
off-node with the Talos recovery keys. Refresh the map after changing claims.
The CSI handle identifies the physical dataset, and a newly created claim
gets a different UID. Capture a mapping without reading Kubernetes Secrets.

```sh
kubectl get pv -o json | jq -r '
  .items[] | select(.spec.csi.driver == "zfs.csi.openebs.io") |
  [.spec.claimRef.namespace, .spec.claimRef.name, .spec.claimRef.uid,
   .spec.csi.volumeHandle, .spec.capacity.storage] | @tsv' > "$PRIVATE_DIR/claims.tsv"
```

1. Fence all writers. Prefer recovering the matching etcd snapshot with its
   original Talos identity, node name and pool GUID. Compare the recovered PVC
   UID, PV handle, OpenEBS ZFSVolume and actual dataset with the saved map
   before admitting workloads. Keep an off-pool copy of current data during
   recovery. [Talos disaster recovery](https://docs.siderolabs.com/talos/v1.13/build-and-extend-talos/cluster-operations-and-maintenance/disaster-recovery)
2. When etcd cannot be recovered, preserve the retained datasets and their
   existing holds. On a trusted recovery system with exclusive access to the
   pool, select and hold a consistent snapshot set. Use the saved map to match
   every expected namespace/claim to exactly one old
   `dpool/k8s/<volume-handle>@<snapshot>`. Record each GUID. Mount read-only
   clones of the selected snapshots at private paths. A recursive snapshot
   creates separate snapshots for descendant datasets. Reading only the
   parent snapshot does not recover their contents. Use application checks
   and native database recovery for crash-consistent snapshots. If a handle
   cannot be identified, recover that namespace/claim by known path from a
   verified Restic snapshot instead of guessing the dataset.
3. Create a **new flat filesystem** below `dpool/migration` such as
   `dpool/migration/rebuild-20261121`. Mount it at
   `/var/mnt/<dataset-name>` with the target POSIX ACL/xattr policy. Keep the
   original migration stage. Size free space for this stage and the new CSI
   datasets, in addition to retained originals. For each claim, make a plain
   `<namespace>/<claim>` directory inside this single filesystem; nested
   mounted datasets would be excluded from the eventual stage snapshot.
   Copy from its read-only clone below and require an empty checksum comparison.
   Run these commands as a privileged recovery operator with the paths
   individually checked against the saved binding map.

   ```sh
   rsync -aHAXS --numeric-ids "$READ_ONLY_CLONE/" "$STAGE/$NS/$CLAIM/"
   rsync -aHAXSnic --delete --numeric-ids "$READ_ONLY_CLONE/" "$STAGE/$NS/$CLAIM/"
   ```

4. For a claim available only through Restic, restore the full pinned
   `<id>:/data/appdata/<namespace>/<claim>` subtree into its empty stage
   directory with `--verify`. Use the legacy xattr treatment for an aggregate
   NFS snapshot. For SparkyFitness, rebuild a complete operable PostgreSQL
   database and uploads from its native archive in isolation, and stop the
   database cleanly before copying its recovered files into the stage.
   Complete independent application checks and record their results.
5. Snapshot this flat stage, hold that snapshot, set the stage read-only, and
   record its actual GUID. Return the pool exclusively to the target if using a
   separate recovery host. Set `MIGRATION_DATASET` to this new dataset and
   supply `MIGRATION_POOL_GUID`, `MIGRATION_SNAPSHOT` and
   `MIGRATION_SNAPSHOT_GUID` for the selected source. Use
   `task platform:foundation`, `MIGRATION_CONFIRM=restore task migration:restore`,
   `task migration:verify` and the explicitly confirmed
   `task platform:handoff` in the order specified by the
   [cutover procedure](truenas-migration.md). Carry the same stage identity
   through verification and handoff. The fresh claims receive fresh CSI
   volumes. Keep old datasets, clones, and holds through a successful
   post-recovery backup and independent restore.

If the repository itself was lost, recover the verified B2 copy into a separate
empty filesystem before attaching it to a server. Validate repository ID,
integrity, workstation snapshots and app snapshot restores there. Recover the
original HTTP authentication file and repository decryption credentials.
Keep the old source, cloud and other recovery copies untouched while choosing
a recovery version. See the [migration runbook](truenas-migration.md) for
independent boot, pool and cold staging recovery.

## Sources

- [Selfhosted backup, server and cloud maintenance](../../../apps/selfhosted/restic/values.yaml)
- [Home automation backup](../../../apps/home-automation/home-automation-backup/values.yaml)
- [Media backup](../../../apps/media/media-backup/values.yaml)
- [Restore task entry points](../../../Taskfile.yaml)
- [Snapshot and claim selection](../../../ansible/roles/restic/filter_plugins/restic_restore.py)
- [Restore transaction](../../../ansible/roles/restic/tasks/execute.yml)
- [Namespace restore Job](../../../ansible/roles/restic/templates/restore-job.yml.j2)

## Related pages

- [Backup and recovery architecture](../architecture/backup-recovery.md)
- [Storage](../architecture/storage.md)
- [Bare-metal migration and recovery](truenas-migration.md)
