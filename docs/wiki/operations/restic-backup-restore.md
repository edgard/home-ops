# Kubernetes Restic restore runbook

Purpose: recover existing Kubernetes appdata and verify the independent copy of the shared Restic repository.
Status: current. Reviewed against: `09ff984c2258c4403ef203631fd580106f839e53` and this revision.

## Repository and backups

The server uses the retained local `selfhosted/restic-repo` claim at
`/var/mnt/dpool/restic`. Its startup checks the pool verification marker for
the current boot, the mounted ZFS filesystem `dpool/restic`, the original
`.htpasswd`, and the decrypted repository ID. Supply the existing
`restic_server_password` and `restic_repository_id` from Bitwarden. Keep the
original repository, HTTP credentials and workstation endpoint during recovery.

Kubernetes clients use `rest:http://restic.selfhosted.svc.cluster.local:8000/`.
The workstation endpoint is `rest:http://restic.edgard.org:8000/`. Record the actual workstation snapshot families and known-good IDs
in that same repository when testing recovery. Only the Kubernetes maintenance job performs retention.

The three namespace backup CronJobs run daily.
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

For the first backup to an intentionally new B2 prefix, keep the scheduled
copy disabled. Verify the decrypted local repository ID and run `restic check`
plus a representative restore. Use a held, read-only point-in-time copy of
the entire repository, including its original `.htpasswd`; this keeps pruning
and clients from changing the source during upload. Confirm the crypt
configuration points to a dedicated unused bucket prefix and successfully
lists it as empty. Use an owner-private working directory on the recovery
machine for both list files. With the verified copy mounted at `$SOURCE`:

```sh
set -eu
umask 077
rclone lsf restic-cloud: --recursive > "$PRIVATE_DIR/remote-objects"
test ! -s "$PRIVATE_DIR/remote-objects"
test -s "$SOURCE/.htpasswd"
rclone lsf --files-only "$SOURCE/snapshots" > "$PRIVATE_DIR/snapshot-ids"
test -s "$PRIVATE_DIR/snapshot-ids"
rclone copy "$SOURCE" restic-cloud: --exclude '/locks/**' --exclude '/snapshots/**' --exclude '/.zfs/**'
rclone copy "$SOURCE/snapshots" restic-cloud:snapshots --files-from "$PRIVATE_DIR/snapshot-ids"
```

For an already populated destination, retain its credentials and existing
data. Verify the repository ID and recover its canaries before permitting
any scheduled copy. If the initial upload stops partway, keep the source
snapshot and inventory; verify the partially uploaded objects against that
source before resuming the same ordered copy.

Before enabling the scheduled copy, use a trusted machine and independent copy
of that configuration to open the B2 repository read-only. For example, set
`RCLONE_CONFIG` to the private configuration file and `RESTIC_PASSWORD_FILE`
to the private repository password file. Supply the expected repository ID
from the independently retained local recovery record. Check a known application
snapshot and a workstation snapshot and restore a representative file from each into private scratch
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
Storage readiness monitors local ZFS maintenance and SMART. Check the
namespace backups and B2 copy separately for missed runs, inspect failed
Job logs and perform periodic independent restore drills. Compare the last
scheduled and successful times against each expected cadence.

```sh
kubectl get cronjobs -A -o custom-columns='NAMESPACE:.metadata.namespace,JOB:.metadata.name,SCHEDULE:.spec.schedule,LAST-SCHEDULE:.status.lastScheduleTime,LAST-SUCCESS:.status.lastSuccessfulTime' | grep -E 'NAMESPACE|home-automation-backup|media-backup|restic-(backup|maintenance)'
```

The schedules and retention counts live in the namespace values linked below. B2 can allow object listings while rejecting downloads with
`403 download_cap_exceeded`. Compare actual bytes or a known digest when
checking recovery. The daily cap also applies to independent restore drills.
[Backblaze data caps](https://www.backblaze.com/docs/cloud-storage-data-caps-and-alerts)

## Restore one application

Use these commands with a running cluster, existing bound claims, the
verified repository server and their owning Argo Applications. The default
preview and Ansible check mode read snapshot metadata. `latest` resolves the
newest matching aggregate or namespace snapshot per application namespace.
The plan displays the full snapshot ID, namespace, claim, destination dataset
and workload replica counts. An explicit snapshot ID pins the source.
Each invocation resolves the current PVC UID, CSI dataset, Helm owner and
Argo tracking identity again. Compare the destination UID and dataset with
the preview before proceeding if a claim may have been recreated.

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

### Preserve the current data before an in-place restore

The hourly ZFS snapshot can predate the last application writes. To preserve
the exact state a restore will replace, run the confirmed playbook in step
mode after reviewing the pinned plan. Set the same explicit `KUBECONFIG` and
`KUBE_CONTEXT` in both terminals. For a single app:

```sh
.venv/bin/ansible-playbook --step ansible/playbooks/restic-restore.yml \
  -e restic_restore_mode=app -e "restic_restore_app=$APP" \
  -e "restic_restore_snapshot=$SNAPSHOT_ID" -e restic_restore_confirm=true
```

Answer `y` through **Require every selected claim to have zero running consumers**.
At **Restore and verify each application**, leave the prompt unanswered. In the
second terminal, save the original plan and snapshot exactly its selected
datasets while the writers, schedulers and Argo controller remain stopped.

```sh
set -eu
umask 077
k() { kubectl --kubeconfig "$KUBECONFIG" --context "$KUBE_CONTEXT" "$@"; }
k -n selfhosted get configmap restic-restore-lock -o json > "$PRIVATE_DIR/restore-lock.json"
jq -er '
  .metadata.uid as $tx | (.data["plan.json"] | fromjson) |
  [.[].claims[] | if .dataset == ("dpool/k8s/pvc-" + .uid)
    then .dataset + "@before-restore-" + $tx else error("unexpected dataset") end] |
  unique | if length > 0 then .[] else error("empty plan") end
' "$PRIVATE_DIR/restore-lock.json" > "$PRIVATE_DIR/rollback-snapshots"
k -n kube-system exec -i deploy/storage-maintenance-health -c check -- sh -ec '
  zfs() { chroot /host /usr/local/sbin/zfs "$@"; }
  test "$(chroot /host /usr/local/sbin/zpool get -Hp -o value guid dpool)" = "$POOL_GUID"
  set --
  while IFS= read -r snapshot; do set -- "$@" "$snapshot"; done
  test "$#" -gt 0
  zfs snapshot "$@"
  zfs hold home-ops-restore "$@"
  zfs get -Hp -o name,value guid "$@"
  zfs holds -H "$@"
' < "$PRIVATE_DIR/rollback-snapshots" > "$PRIVATE_DIR/rollback-proof"
```

Check the saved GUID and hold for every snapshot before answering `c` to
continue. A failure leaves the restore paused for inspection. To recover
the pre-write version, stop all restore Jobs and consumers and compare the
saved snapshot and destination identities. On a fenced dataset whose checkpoint
is still the newest snapshot, `zfs rollback "$snapshot"` discards later file
changes. When newer snapshots exist, keep them and recover the held source
through a read-only clone and checksum-verified copy. Verify every selected
claim and the application before resuming its writers. Release the holds and
retire selected rollback snapshots only after acceptance.
[OpenZFS rollback](https://openzfs.github.io/openzfs-docs/man/master/8/zfs-rollback.8.html)
and [Ansible step mode](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_startnstep.html)

## Restore all appdata

```sh
task restic:restore-all
task restic:restore-all confirm_restore=true
```

An explicit historical aggregate snapshot can cover all namespaces. To pin
different modern snapshots in one transaction, save a private JSON object
mapping each selected namespace to the full ID from its preview. Use the
same file for both invocations.

```sh
task restic:restore-all snapshot="$(jq -c . "$PINS")"
task restic:restore-all snapshot="$(jq -c . "$PINS")" confirm_restore=true
```

A modern
snapshot from one namespace cannot restore another namespace. Restore-all
requires its planned namespace/claim names and Argo owners to match the
current Helm-rendered appdata inventory, with the declared exclusions. Full
preview therefore needs access to the pinned app chart. Single-app recovery
uses its live Argo resource inventory. Media, repository storage
and SparkyFitness have their own recovery procedures.

## SparkyFitness database and files

SparkyFitness's native full archives contain a compressed SQL dump and an uploads
archive. Restic excludes the live PostgreSQL subdirectory. Restoring its PVC as
files therefore does not restore the database. For a running installation, recover
the selected completed archive into a temporary directory and use the native
administrator restore page, retaining the same Bitwarden encryption/auth secrets.

For a stopped or damaged application on a cluster already managed by Argo, use this manual application-specific sequence:

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

The ordinary in-place restore excludes both the SparkyFitness app and its data
claim, including during restore-all. The fresh-claim path can recover its files
before a separate native database import.

## New cluster or lost etcd state

Keep the Talos identity, current etcd snapshots, the pool and dataset GUIDs,
the PVC-to-CSI binding map and independent Restic credentials off the node.
Refresh the map after claim changes. Capture it without reading Kubernetes
Secrets. Record native ZFS dataset GUIDs beside these handles.

```sh
kubectl get pv -o json | jq -r '
  .items[] | select(.spec.csi.driver == "zfs.csi.openebs.io") |
  [.spec.claimRef.namespace, .spec.claimRef.name, .spec.claimRef.uid,
   .spec.csi.volumeHandle, .spec.capacity.storage] | @tsv' > "$PRIVATE_DIR/claims.tsv"
```

When matching etcd state survives, fence writers and recover that state with
its Talos identity. Verify the recovered node, pool and the live PVC, PV,
ZFSVolume and native dataset identities against the saved map before allowing
writers. [Talos recovery procedure](../architecture/talos-bootstrap.md#recover-the-existing-control-plane)

When rebuilding without etcd, keep all original datasets, source snapshots
and holds. Give the recovery node exclusive access to the pool. Run
`task platform:foundation` and `task platform:claims` before releasing
Argo. These steps prepare a private read-only repository endpoint and the
current chart-owned claims. Each prepared PVC gets its own new CSI handle.
Size the pool for both retained originals and the new filesystems.

### Restore a freshly prepared claim

Choose the complete 64-character snapshot ID that covers the namespace. Read
the PVC UID from that cluster. Use the same ID and UID for preview and execution.

```sh
claim_uid=$(kubectl -n "$namespace" get pvc "$claim" -o jsonpath='{.metadata.uid}')
task restic:recover-claim namespace="$namespace" claim="$claim" uid="$claim_uid" snapshot="$snapshot"
task restic:recover-claim namespace="$namespace" claim="$claim" uid="$claim_uid" snapshot="$snapshot" confirm_restore=true
```

The role checks the foundation ownership annotation, exact PVC/PV and CSI
volume, absent GitOps owners and consumers, private read-only repository,
and the actual snapshot directory. The Job checks its mounted ZFS source
and requires an empty destination immediately before restoring. It reads the
repository without locking through the read-only endpoint and verifies the
restored subtree. The cluster-wide recovery lock excludes handoff and other
restore operations. Inspect `restic-recover-<PVC-UID>` in the target namespace
for the result. A failed execution retains its Job and lock for inspection.
If its Job failed after starting, preserve the partial contents for inspection
and prepare a fresh verified destination. If the Job completed and only the
checkpoint or lock release was interrupted, verify its UID, source annotation,
successful Restic verification, unchanged destination and absence of writers.
Keep the exclusive lock while checking an existing automatic proof or taking
a held destination snapshot and documenting independent manual verification
for the same PVC. Clear only the inspected lock, using its recorded UID.
Use native database and application checks before approving recovered data.

If usable data survives only on a retained CSI dataset, select its held
snapshot by the saved handle and GUID. Access that snapshot read-only on
a trusted recovery host or recovery Job. Verify the source mount and the
empty new claim's CSI identity before copying. Preserve numeric owners,
hardlinks, sparse files, portable xattrs and POSIX ACLs, and leave SELinux
labels under the target policy. Run the checksum dry-run against the same
read-only source and require successful execution with empty itemized output.
These commands assume both roots were independently verified.

```sh
rsync -aHAXS --numeric-ids --filter='-x system.*' --filter='-x security.selinux' "$source/" "$target/"
rsync -aHAXSnic --delete --numeric-ids --filter='-x system.*' --filter='-x security.selinux' "$source/" "$target/"
```

For SparkyFitness before first Argo handoff, restore the claim subtree to
recover its uploads and completed archives. Run the following recovery with
application deployments and their Services still absent.

1. Apply the checked-in [SparkyFitness ExternalSecret](../../../apps/selfhosted/sparkyfitness/manifests/sparkyfitness-credentials.externalsecret.yaml)
   and wait for its `Ready` condition. The Bitwarden entries must contain
   the original database owner credential and application encryption keys.
2. Start one temporary PostgreSQL-only Pod in `selfhosted` using the
   digest-pinned official image, database owner Secret reference, security
   context, `PGDATA` and `postgresql` PVC subpath from the
   [PostgreSQL controller values](../../../apps/selfhosted/sparkyfitness/values.yaml).
   Bind only a local Unix socket with `postgres -c listen_addresses=''`.
   Verify the mount belongs to the expected new CSI volume before PostgreSQL
   initializes. Use a private working directory for archive extraction and
   read the archive from the same restored claim.
3. For an ordinary completed full archive, extract its gzipped plain SQL
   and uploads tar. Initialize the target database with its expected owner.
   Create the `sparky_app` role if necessary, restore SQL over the local
   socket through `psql --set ON_ERROR_STOP=1`, and restore uploaded files
   with the backend's expected ownership. A separately recorded custom-format
   PostgreSQL dump uses `pg_restore --exit-on-error` and its separately saved
   global roles. Match the archive format before choosing the command.
4. Check recovered schema, nonempty expected records and representative
   upload hashes. Stop PostgreSQL cleanly, remove its temporary Pod and all
   recovery consumers, and capture the verified destination snapshot for
   handoff. If SQL import or upload verification stops partway, preserve
   the original archive, inspect the isolated database and partial files,
   and repeat the import into a clean destination. Record `native-postgresql`
   only after both checks pass. The normal deployments start after release.

A successful cold Restic Job for an ordinary claim automatically takes a
destination snapshot, holds it and records the restored source and current
volume identity in an immutable ConfigMap. For manual retained-data copies
and SparkyFitness, stop all recovery consumers after application checks,
take a destination snapshot, hold it and record its GUID. Supply manual
entries in the owner-private `PLATFORM_RECOVERY_FILE` JSON object with
decimal-string `pool_guid` and a `claims` array.
Each entry records `namespace`, `name`, new PVC `uid`, `dataset_guid`,
destination `snapshot` basename, `snapshot_guid` and `verification`. Manual
entries use `retained-checksum` or `native-postgresql`. The automatic checkpoint
uses `restic-verify`. SparkyFitness
requires the native method. Every current claim must have exactly one
accepted automatic or manual proof. The first `task platform:handoff` checks the
held snapshot, unchanged destination and complete claim inventory before
starting writers. Preserve the independent recovery sources through a new
backup and tested restore. [Platform bootstrap and handoff](../architecture/talos-bootstrap.md)

If the local repository was lost, recover the verified B2 copy into an empty
filesystem and verify the decrypted repository identity, workstation and
application snapshots and representative restores. Recover the original HTTP
authentication file and decryption credentials before attaching the server.
Keep the cloud copy and other recovery sources intact throughout selection.

## Sources

- [Selfhosted backup, server and cloud maintenance](../../../apps/selfhosted/restic/values.yaml)
- [Home automation backup](../../../apps/home-automation/home-automation-backup/values.yaml)
- [Media backup](../../../apps/media/media-backup/values.yaml)
- [Restore task entry points](../../../Taskfile.yaml)
- [Snapshot and claim selection](../../../ansible/roles/restic/filter_plugins/restic_restore.py)
- [Restore transaction](../../../ansible/roles/restic/tasks/execute.yml)
- [Restore a new claim before handoff](../../../ansible/roles/restic/tasks/cold.yml)
- [Namespace restore Job](../../../ansible/roles/restic/templates/restore-job.yml.j2)

## Related pages

- [Backup and recovery architecture](../architecture/backup-recovery.md)
- [Storage](../architecture/storage.md)
- [Platform bootstrap](../architecture/talos-bootstrap.md)
