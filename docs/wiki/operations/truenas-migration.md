# Move the TrueNAS-hosted cluster onto bare-metal Talos

Purpose: stage the existing appdata while the old VM is stopped, recover the
shared datasets on bare metal, and retain a bootable TrueNAS rollback on the
same SSD.
Status: current. Reviewed against: `d80872c8700249ef67aa42919e297c37e75faef3`.

The source tasks run on the operator Mac and use its strict-host-key SSH
connection to TrueNAS. They capture a consistent ZFS snapshot, a native
read-only staging copy on the surviving HDD pool, and two parts of the SSD
recovery bundle. Actual disk identities, measurements, credentials, backup
locations, and verification results belong in the operator's private records.

## Which revision runs where

The preparation PR adds only operator tools and documentation. It can be merged
while the VM is serving workloads. Record its merged commit as the rollback
revision. The separate bare-metal cutover PR changes the ApplicationSet's
discovered apps. Keep that PR open until the old VM, fileservices and other
writers are fenced. After the SSD backup and physical checks, merge the cutover
PR and check out the clean merged `master` on the Mac before bootstrapping the
target foundation. Foundation verifies that local HEAD equals remote master.

## Prepare recovery while everything is online

1. Use an encrypted, durable operator directory outside this checkout. Set
   directory mode `0700` and config mode `0600`. Keep the TrueNAS configuration
   download **with password secret seed**, any dataset or SED keys, and a tested
   physical-LAN administrative login there. Check which dataset supplies the
   SSH user's home. The TrueNAS system dataset and home dataset must both be
   available on rollback. Save the VM device/firmware definition, EFI boot
   entry and loader path, network/DHCP reservations, share ACLs and service
   enables so their original settings can be restored.
2. Save a fresh etcd snapshot off-node, verify that its status is readable, and
   use the existing [secret recovery procedure](secrets-maintenance.md) to test
   Bitwarden and the original Talos identity. Preserve separate operator copies
   of the previous Talos client config, kubeconfig and machine config.
3. Check the original Restic repository ID, appdata and workstation snapshot
   families, and a representative restore to a private scratch directory. For
   the TrueNAS B2 mirror, preserve the bucket/prefix, key credentials, rclone
   crypt password, salt and filename-encryption setting in the operator's
   secret manager. From the Mac, read the encrypted remote with those settings
   and restore from a known snapshot. Compare a known file hash. Run a final
   mirror only after backup and pruning have finished. A repository mirror
   contains only the data actually backed up by those clients. Separately
   account for shared media, other NAS datasets and changes since the backup.
4. Inventory live PVs and actual application-directory sizes. Include retained
   claims whose app has been retired. Capture root and representative descendant
   numeric ownership, modes, ACLs, xattrs, file counts and hardlinks, alongside
   fresh application-native database backups. Verify SparkyFitness SQL/uploads
   and application encryption keys using the [Restic runbook](restic-backup-restore.md).
   NFSv4 ACLs from TrueNAS need an effective access test on the target,
   including denied access. Do this before opening a migrated share.
5. From TrueNAS, record `zpool list -Ho name,guid,health`, `zpool status -LP`,
   `lsblk -b -o NAME,START,SIZE,LOG-SEC,PARTUUID,FSTYPE`, the stable whole-disk
   by-id path, and `efibootmgr -v`. Inspect current SMB and NFS exports, their
   clients, snapshot schedules, scrubs, SMART tests, cloud tasks and alerts.
   Verify the replacements or explicit retirement of each. TrueNAS's SSH and
   file services depend on the source OS. Set up the LAN management and
   workstation recovery paths before stopping it.

Create `source.json` using your verified values. All three ZFS pool GUIDs
are decimal **strings**. The source dataset and recovery parent are direct
children of different pools. The recovery parent is a **new, unshared dataset**.
Include the in-place surviving datasets that need rollback snapshots in
`hold_datasets`. A mounted share and a subdirectory of it are unsuitable
destinations for the private partition archive.

```json
{
  "source_host": "operator@nas.example",
  "source_dataset": "spool/appdata",
  "recovery_dataset": "dpool/migration",
  "hold_datasets": ["dpool/media", "dpool/restic"],
  "snapshot": "baremetal-cutover",
  "vm": "old-cluster",
  "ssd_by_id": "/dev/disk/by-id/ata-REPLACE",
  "spool_partuuid": "00000000-0000-4000-8000-000000000001",
  "boot_guid": "1000000000000000001",
  "spool_guid": "1000000000000000002",
  "data_guid": "1000000000000000003"
}
```

```sh
export MIGRATION_CONFIG="$HOME/private/home-ops-cutover/source.json"
task migration:preflight
evidence="$(dirname "$MIGRATION_CONFIG")"
jq '.geometry | {disk_bytes, sector_bytes, prefix_bytes, partition_bytes, tail_bytes,
    full_coverage: (.prefix_bytes + .partition_bytes + .tail_bytes == .disk_bytes),
    mac_bytes: (.prefix_bytes + .tail_bytes)}' "$evidence/preflight.json"
```

Preflight requires an already trusted SSH host and an administrative SSH session
that can run the role's Python under noninteractive sudo. It performs reads on
the source. Its private report records disk GUID, partition GUIDs, starts,
lengths, logical sector size, current referenced appdata and available HDD
space. Compare pool GUIDs against the independent inventory. Reserve HDD space
for staging, new app claims, snapshots and the **entire final SSD partition**
backup. Reserve Mac space for `prefix_bytes + tail_bytes`. Recheck free space
immediately before both captures. Use a fresh private config directory for a
new cutover session.

## Stop writers and stage appdata

1. Announce the outage. Pause Argo reconciliation in the source cluster,
   suspend data-writing CronJobs, prevent new external writes, stop app
   controllers and databases cleanly, finish the final backups, and record
   snapshot IDs. Stop workstation Restic jobs too. Disable the old VM's
   autostart, then shut it down gracefully. Wait for TrueNAS to report
   `STOPPED`. Suspend TrueNAS cloud sync and wait for a running transfer to
   finish. Stop SMB and NFS and disable their autostarts. Keep physical LAN
   SSH or console access. Preserve two config exports: original settings, and
   this recovery configuration with writers disabled.
2. Run `MIGRATION_CONFIRM=stage task migration:stage`. This takes and holds the
   named snapshot of the source appdata and each listed surviving dataset. It
   receives the appdata snapshot on TrueNAS into `dpool/migration/appdata`,
   verifies the replication snapshot GUID and relevant filesystem properties,
   and records the source/destination identity in private `stage.json`. Read
   `held_snapshot_guids` and verify the expected datasets are present. The
   receipt also reports `acl_inventory` for the held snapshots. Review the
   checked entry counts, nontrivial ACL counts and private example paths.
   Resolve any nontrivial NFSv4 grants or denials before authorizing the SSD
   overwrite. Check that target workload IDs retain the intended access.
   The receive sets the staged dataset read-only. Keep the original untouched for
   recovery. Snapshotting separate pools uses the preceding writer shutdown
   to establish an application-consistent cutoff.
3. Inspect the staged snapshot's namespace/claim layout. Compare representative
   files, a database dump, media hardlinks, ACLs and ownership against the
   inventory. Verify the selected cold snapshot includes any retained
   but inactive application directory. A target PVC is sized against real
   usage and future growth. Continue only after the staged data is readable.
4. While the source HDD pool is online, you can create the new empty OpenEBS
   parent here. Verify the recorded GUID, check that `dpool/k8s` is absent,
   then run `zfs create -o mountpoint=none -o acltype=posix -o xattr=sa dpool/k8s`
   on TrueNAS. Record its dataset GUID and properties. A pre-existing parent
   requires inspection. OpenEBS and its PVCs are created on the new cluster.
5. Release any remaining references to the SSD data pool. Stop any source
   services using it and suspend scheduled snapshot jobs. Cleanly export
   **only the SSD data pool**, with its configuration and data preserved. Use
   the pool name and GUID in the private report. Do not select destroy, cascade
   removal of shares, wipe or force-export. Keep the HDD pool mounted on
   TrueNAS; it holds the recovery location and may hold the live system dataset.
   On TrueNAS 25.10 use **Storage → Export/Disconnect** on this SSD pool.
   Leave both **Destroy data on this pool** and **Delete saved configurations
   from TrueNAS** clear. Wait for the job to finish and confirm the pool is
   absent from `zpool list`. If a reference blocks export, resolve the listed
   attachment with the VM and file services still stopped.
6. Run `MIGRATION_CONFIRM=archive task migration:archive`. The role checks the
   exported pool's label, final partition GUID, expected boot disk and geometry
   again. It copies the entire cold partition to
   `<recovery-dataset mountpoint>/spool.partition.raw`, fsyncs it, verifies its
   size and SHA-256 by reading it back, and publishes it without overwriting an
   existing file. Save private `archive.json` off the NAS. The archive contains
   the original appdata, VM zvol, pool GUID, snapshots, and residual data from
   the partition. Restrict access accordingly.
7. Gracefully shut down TrueNAS. Wait for power-off before pulling the SSD.
   Leave the HDD members together. On the Mac, attach only the source SSD
   being prepared. Identify the external whole disk with `diskutil list` and
   `diskutil info`, check its physical size and logical sector size, then
   unmount its partitions using `diskutil unmountDisk /dev/diskN`.

## Capture the Mac boot bundle and install

```sh
export MIGRATION_MAC_DISK=/dev/diskN
MIGRATION_CONFIRM=boot-backup task migration:boot-backup
jq '.ranges' "$HOME/private/home-ops-cutover/boot-backup.json"
```

The backup reader opens only an external physical disk. It verifies both GPT
checksums and every partition against the TrueNAS inventory. It saves and
hash-verifies `boot-prefix.raw` and `backup-gpt.raw` in the private directory.
The prefix includes the protective MBR, primary GPT, BIOS/EFI data, TrueNAS
boot-pool and any intervening swap. The original partition numbers can be
out of physical order. The middle is the cold SSD data partition already on
the HDD pool. The tail contains the secondary GPT. The three lengths must
sum to the recorded SSD size. If the device requires elevated read access,
authorize the local read-only `dd` operation for this session.

Keep the original bundle private and verify the recorded EFI loader exists on
the original ESP. Record how to select it on the headless machine if the UEFI
boot order changes. Before writing Talos, compare the downloaded Image Factory
RAW checksum to its published checksum and verify the machine schematic and
version against the intended upgrade installer. Re-identify the external disk
immediately before writing, flash only that SSD, and verify the image readback.
Use the bare-metal profile and the independent LAN maintenance address. Boot
with the pool disks isolated until the intended ZFS import behavior has been
verified against sacrificial storage. The extension can auto-import visible
pools; connecting production disks is a separate operator action.

## Bring up the new cluster

1. Verify the bare-metal drive, physical NIC, firmware, bridge, maintenance
   and final control-plane addresses, DNS, NTP and Talos API from the physical
   LAN. Check the generated disk selector, versions and schematic. Bootstrap
   only the Talos node and Kubernetes API using the
   [Talos bootstrap guide](../architecture/talos-bootstrap.md). Keep Argo and
   data writers stopped. Power down before attaching the surviving HDDs.
   Boot and inspect `talosctl -n "$NODE" get extensions`, `talosctl -n "$NODE"
   services`, `talosctl -n "$NODE" logs ext-zfs-service`, and
   `talosctl -n "$NODE" mounts`. The service imports all visible pools and can
   force an import. Use disks exclusively attached to this fenced host.
2. Perform the mount and ACL procedure below. Meet the identity, reboot and
   copy prerequisites before launching the storage foundation.

### Mount the surviving datasets

From the Mac, start one privileged debug shell on the physical node. Set
`DEBUG_IMAGE` to an approved Linux image with util-linux `nsenter`, or use a
local image tarball for offline bootstrap. The release Talos CLI starts the
container with host PID visibility and a separate mount namespace. Run the
host ZFS binaries in PID 1's mount namespace and root:

```sh
talosctl -n "$NODE" debug "$DEBUG_IMAGE" --args /bin/sh
```

```sh
host() { nsenter --mount=/proc/1/ns/mnt --root=/proc/1/root -- "$@"; }
zpool() { host /usr/local/sbin/zpool "$@"; }
zfs() { host /usr/local/sbin/zfs "$@"; }
zpool list -Hp -o name,guid,health
zpool status -LP dpool
zpool get -H -o property,value altroot dpool
zfs get -Hr -t filesystem -o name,property,value,source mountpoint,canmount,sharenfs,sharesmb dpool
```

Match the pool GUID to `data_guid` and every member to the source inventory.
If the pool has not imported, inspect `zpool import` and the extension logs.
Once the importer is idle and the pool is exclusively attached, a manual
`zpool import -N "$DATA_GUID"` selects that specific GUID without mounting its
filesystems. Investigate any request to force import, a missing member,
encryption lock, or unknown feature before changing a property.

Save the displayed property table privately **before changing anything**.
The source's original table and import prefix are also in `preflight.json`.
With workloads fenced, plan only the datasets that need mounting. Keep
unneeded datasets, including TrueNAS system datasets with special or legacy
mountpoints, offline if they conflict with Talos. Record each such change
by name and property. For example, `zfs set canmount=noauto DATASET` prevents
an automatic mount; cleanly unmount it separately if currently mounted.
Keep share properties disabled on the target. Check the host mount table
and underlying target directories for existing data before remapping.

For the example layout below, these three independent mounts suffice. The
stage child normally inherits its parent's path. Confirm each dataset is a
filesystem, its source and properties match the private inventory, and each
target is absent or empty on the correct parent. Apply changes one at a time,
recording each previous value **and property source**. A local mountpoint on
a child overrides inheritance and requires its own explicit remap if needed.

```sh
zfs set mountpoint=/var/mnt/dpool/media dpool/media
zfs set mountpoint=/var/mnt/dpool/restic dpool/restic
zfs set mountpoint=/var/mnt/dpool/migration dpool/migration
zfs get -H -o name,property,value,source mountpoint,mounted,readonly dpool/media dpool/restic dpool/migration dpool/migration/appdata
```

If a required filesystem shows `mounted=no`, inspect its `canmount`, mountpoint
and any parent mounts. Use `zfs mount DATASET` for that verified filesystem.
Its automatic mounts must work after reboot too. Ensure the stage remains
read-only. Check that `/proc/1/mountinfo` shows the exact dataset name and ZFS
filesystem at each required path.

### Create the OpenEBS parent

If Phase 1 created `dpool/k8s`, check its recorded GUID and properties and
verify it has no children before first provisioning. Leave its mountpoint
at `none`. For a deferred creation, use the following procedure.

On the same verified pool, check `zfs list -H -o name -r dpool` before
creating the new parent. Use a new empty `dpool/k8s` with POSIX ACLs and
extended attributes for app PVCs. Keep each existing shared dataset's ACL
model intact. For case-sensitive source appdata and a Linux target:

```sh
zfs create -o mountpoint=/var/mnt/dpool/k8s -o acltype=posixacl -o xattr=sa -o sharenfs=off -o sharesmb=off dpool/k8s
zfs get -H -o name,property,value,source acltype,xattr,casesensitivity,normalization dpool/migration/appdata dpool/k8s
```

On a retry, verify the existing parent's identity, children and properties.
If the source uses different case or Unicode semantics, specify compatible
creation-time settings before the first claim. Native ZFS send preserves the
original ACL data on the stage. Linux POSIX ACLs cannot represent arbitrary
NFSv4 allow/deny, ordering or inheritance. Inspect descendant ACLs on
TrueNAS. For nontrivial ACLs, translate effective grants into a separately
reviewed POSIX policy and verify representative allow **and deny** accesses
under actual workload IDs before handoff. Keep the immutable staged copy.
If the target cannot read the stage's security metadata, finish that
translation with the source tooling before permitting writers.

Reboot with `talosctl -n "$NODE" reboot`. Verify `talosctl -n "$NODE" mounts`
in the new boot, recheck the GUID and observe the missing-pool fail-closed
behavior on the isolated rehearsal. With the dormant target manifests
selected on this cluster and the source identities set, run
`task platform:foundation` before the restore. This installs the platform
without admitting application writers.

### Restore and hand off

1. Pass the preserved identities into the target migration. Use the actual
   private evidence directory in these examples.

   ```sh
   evidence="$(dirname "$MIGRATION_CONFIG")"
   export MIGRATION_POOL_GUID="$(jq -er .pool_guid "$evidence/stage.json")"
   export MIGRATION_SNAPSHOT="$(jq -er .snapshot "$MIGRATION_CONFIG")"
   export MIGRATION_SNAPSHOT_GUID="$(jq -er .snapshot_guid "$evidence/stage.json")"
   MIGRATION_CONFIRM=restore task migration:restore
   task migration:verify
   ```

2. Verify all required app PVCs, data/ownership checks, Restic repository ID,
   retained workstation snapshots and application-specific canaries before
   `task platform:handoff`. Recheck name resolution, external workstation
   backups through the existing Restic REST endpoint, one application restore,
   media read/write roles and hardlinks, and a cold reboot. Only one cluster
   may own the original addresses. Enable one set of backup and maintenance
   jobs after a successful restore drill. Keep B2 writes disabled until a
   cutover-compatible repository has been verified and its restore tested.
   Keep the held snapshots and SSD recovery pieces through acceptance.

## Roll back to TrueNAS on the same SSD

1. Fence the new cluster, cloud synchronization, and all data writers.
   Keep the old VM offline. Revert the cutover configuration through a PR
   against `master` and verify the resulting ApplicationSet inputs match the
   recorded source revision before allowing the old Argo controllers to run.
   Both clusters follow the same Git branch.
   Choose the rollback point explicitly. Capture and reconcile any required
   changes made since cutover before restoring the old state. Preserve a
   target etcd snapshot and the new app data separately if they are needed
   for this handback. Confirm the original HDD pool and archived partition
   remain readable, and that the Mac files and private receipts are intact.
2. Before leaving Talos, restore the original properties marked as changed in
   the journal, with writers still fenced. For an original local value use
   `zfs set property=original-value dataset`. For an originally inherited or
   default value use `zfs inherit property dataset`; use `zfs inherit -S property
   dataset` when the original source was received. For a non-inheritable
   property such as `canmount` restore the recorded value explicitly as needed.
   Some original TrueNAS mountpoints cannot mount on Talos. If applying those
   would remount a busy or unsupported path, keep it unmounted and restore
   the remaining properties from the TrueNAS console before bringing any
   client or share online. Account for TrueNAS's import altroot when comparing
   effective paths. Recheck all changed values against the journal and keep
   the source system dataset and operator home available on TrueNAS.
3. Gracefully shut down the bare-metal node. Put the SSD on the Mac and
   independently recheck physical identity, disk size and sector size against
   `preflight.json`. Talos has changed its GPT. With that disk unmounted and
   your source files hash-verified, write **only** the saved boot prefix at byte
   zero and the secondary GPT at its recorded offset. These two writes
   intentionally replace the Talos boot layout. Use raw-device byte ranges
   from `boot-backup.json` and leave the middle partition alone on the Mac.
   Sync and read back the same ranges. Confirm both SHA-256 values, the GPT
   disk GUID, and every partition UUID and extent before powering on the NAS.
4. Refit the SSD alongside the original HDDs, boot the saved TrueNAS UEFI
   loader, and keep VM autostart, SMB/NFS and B2 sync disabled. If the HDD
   pool needs importing, select the recorded **existing** GUID, preserving its
   data and original TrueNAS mount prefix. Verify the expected system and
   operator-home datasets, SSH access, and recovery dataset mount. Never
   create an HDD pool as part of this recovery.
5. On TrueNAS, verify the archive file's byte count and SHA-256 against
   `archive.json`. Resolve the original SSD by-id, then the final partition
   by its recorded PARTUUID. Require that it belongs to this SSD, has the
   expected size, and is neither the TrueNAS boot partition nor an HDD. If
   surviving labels made the SSD data pool appear imported, verify its identity
   and cleanly export it first. Restore the verified partition file **only
   to this partition** while it is unmounted/unimported. Flush writes and hash
   the complete destination partition before importing it. These steps restore
   the original pool labels and GUID without needing ZFS access from macOS.
   For example, resolve `readlink -f "/dev/disk/by-partuuid/$SPOOL_PARTUUID"`
   and confirm its parent with `lsblk -dnro PKNAME "$PARTITION"` against the
   resolved original SSD by-id. Confirm `blockdev --getsize64 "$PARTITION"`
   equals `archive.json`'s byte count. After explicitly approving those
   checks, use `dd if="$ARCHIVE" of="$PARTITION" bs=8M conv=fsync status=progress`
   on TrueNAS. Require `sha256sum "$PARTITION"` to match the archive receipt
   and `zdb -l "$PARTITION"` to report the original spool GUID. Then use
   **Storage → Import Pool** to import that existing pool through TrueNAS.
6. Confirm the original source pool identity, VM disk path, application
   datasets and NFS export paths. Verify access and permissions through the
   original NFS addresses before starting the old VM. Enable its original
   SMB/NFS services as required. If an exported attachment is missing, use
   the saved, writer-disabled pre-export configuration to recover it and
   recheck the VM zvol and share paths before starting the VM. Enable the VM's
   resources and applications once, verify its API, mounted PVCs, Restic
   service and app state, then explicitly resume the chosen schedules and
   client services. Retain all cold copies until the rollback is accepted.

The snapshot and archive jobs are rerunnable with the same configuration.
Incomplete jobs do not publish a completed receipt. An identity conflict or
an existing destination with different contents requires operator inspection.
Recovery artifacts, snapshot holds, the VM and old datasets require a separate
cleanup decision after the rollback window.

## Sources

- [Source playbook](../../../ansible/playbooks/migration-source.yml) and [source operation entry point](../../../ansible/roles/truenas_migration/files/source_operator.py)
- [TrueNAS staging and archive checks](../../../ansible/roles/truenas_migration/files/source.py)
- [Current storage definitions](../../../apps/kube-system/nfs-provisioner/values.yaml) and [Restic service configuration](../../../apps/selfhosted/restic/values.yaml)
- [TrueNAS configuration recovery](https://www.truenas.com/docs/scale/25.10/scaletutorials/systemsettings/advanced/managesysconfig/) explains the password secret seed.
- [TrueNAS pool management](https://www.truenas.com/docs/scale/25.10/scaletutorials/storage/managepoolsscale/) documents the export and configuration removal options.
- [TrueNAS cloud encryption](https://www.truenas.com/docs/scale/25.10/scaleuireference/dataprotection/cloudsynctasksscreensscale/) describes remote encryption and filename settings.
- [OpenZFS send](https://openzfs.github.io/openzfs-docs/man/master/8/zfs-send.8.html) documents snapshot streams and property replication.
- [Talos privileged debug implementation](https://github.com/siderolabs/talos/blob/v1.14.6/internal/app/debug/debug.go) documents host PID access in the release debugging profile.
- [Talos ZFS extension](https://github.com/siderolabs/extensions/tree/main/storage/zfs) documents import behavior and compatible mount paths.

## Related pages

- [Talos and platform bootstrap](../architecture/talos-bootstrap.md)
- [Storage and shared media](../architecture/storage.md)
- [Backup and recovery](../architecture/backup-recovery.md)
- [Restic restore procedure](restic-backup-restore.md)
