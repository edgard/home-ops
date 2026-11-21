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
PR into `master` (retarget the stacked PR after preparation merges) and check
out the clean merged `master` on the Mac before bootstrapping the
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
   Resolve nontrivial ACLs on datasets that will serve workloads before the
   SSD overwrite. Retain the original policy on datasets kept offline. Check that target workload IDs retain the intended access.
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
7. Gracefully shut down TrueNAS. The [headless USB option](#leave-the-ssd-in-a-headless-host)
   keeps the SSD installed. For the Mac enclosure route, wait for power-off before pulling the SSD.
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
boot order changes. The reviewed image is the [v1.14.6 amd64 metal RAW from Image Factory](https://factory.talos.dev/image/39699a54506a4570606671d813387abadbba0767ec91769b57e993f3387795d9/v1.14.6/metal-amd64.raw.zst).
Match its schematic and version to the cutover installer. These SHA-256
values were measured from that HTTPS download. The public Factory returned
HTTP 402 for its separate checksum endpoint. The uncompressed GPT contains
the amd64 EFI fallback loader at `EFI/BOOT/BOOTX64.EFI`.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Compressed RAW | 126707234 | `2a78c0531dc3ae45a9f6bf5f4199bba5a6c947bbf7924f12e0d3bb8a73296edc` |
| Uncompressed RAW | 2355101696 | `48e4d424951748986c14f39374f747dd35b6f38fa24a4674e82a4bc1354dd877` |

Verify the compressed file with `shasum -a 256` and `zstd -t`.
For this reviewed build, `zstd -dc IMAGE.raw.zst | shasum -a 256` must match
the uncompressed hash. A new version or schematic needs its own evidence.
**Operator disk write:** after confirming all three backup pieces, reidentify
the external whole SSD by geometry and GPT and unmount it. The image covers
only the start of the larger SSD. Its write leaves the former secondary GPT
and ZFS labels outside that range. With the identified SSD in its Mac
enclosure, clear the old SSD signatures and its original backup GPT before
writing the RAW. For an installed SSD, use the headless procedure below.
A full zero-fill of this verified SSD is one option. This is the point at
which recovering TrueNAS requires the saved three-piece bundle. Flash the
reviewed RAW to that same whole device. Sync and read back the first 2246 MiB before boot, for example
`sudo dd if=/dev/rdiskN bs=1m count=2246 | shasum -a 256` on the Mac.
Require the same uncompressed hash and eject the disk cleanly.
On a headless host, confirm how firmware will reach the RAW image's EFI loader
and how you will regain control if the NIC never receives its maintenance
lease. Verify the fallback loader on the SSD and retain the tested original
boot-entry recovery path. Use the bare-metal profile and the independent LAN
maintenance address. Rehearse the intended ZFS import behavior on disposable
storage before booting with the surviving HDDs attached. The first machine
configuration must restrict automatic import while those disks are present.

### Leave the SSD in a headless host

An independent Linux rescue USB can capture the same boot bundle over Ethernet
and write the reviewed Talos RAW directly to the internal SSD. TrueNAS recovery
is a rollback procedure. The forward migration can use the installed, fenced
TrueNAS system briefly to select the rescue USB if the firmware boots the SSD first.

1. Prepare an amd64 UEFI rescue stick with wired DHCP, the physical NIC driver
   and firmware, key-only SSH and a host key pinned on the Mac. For SystemRescue,
   include `copytoram` and `nomdlvm` in the default kernel command line.
   Rehearse boot and SSH on the finished image, then read the written USB back.
2. Check firmware Secure Boot compatibility. Match the USB's partition
   signature and EFI loader to the firmware's existing entry. If an entry is
   missing, the current OS can register it with `efibootmgr --create-only`.
   Select it as `BootNext`, preserving the normal boot order. Record the
   original and requested entries. Keep the source
   services fenced if booting TrueNAS for this step.
3. After USB boot, authenticate the SSH host key and confirm UEFI, the expected
   physical NIC, the RAM-backed root, inactive swap, and no active ZFS, MD or
   device-mapper consumers of the drives. The HDDs can stay attached during
   rescue. Match each disk and partition to the original inventory, including
   WWNs, serial numbers, sizes and partition UUIDs. Set each HDD and each of
   its partitions read-only using Linux block-device controls. Read the flags
   back and require all of them before capture and again before the SSD write.
   Alternatively, disconnect the HDDs while powered off. Match the SSD's
   stable ID, serial, size and both GPTs to preflight, verify it has no mounts
   or active holders, and keep an exclusive handle on the identified SSD.
   Linux's read-only flags expire on reboot.
4. From the Mac, stream the exact prefix and secondary GPT ranges from that
   cold SSD to private local files. Verify their byte counts and independent
   SHA-256 readbacks. Hash the middle partition on the NAS and compare it to
   the archive receipt. The repository's `migration:boot-backup` command
   targets a locally attached macOS disk; the rescue route needs a verified
   Linux reader and the same range and identity checks.
5. After accepting the three recovery pieces, write the reviewed Talos image
   using the same SSD identity, signature-clearing and readback checks as the
   enclosure route. From rescue, verify Talos's new EFI partition and loader,
   and select it for the next boot. Keep the rescue USB available until the
   physical Talos API responds. If the HDDs remain attached, use the guarded
   first configuration below before starting CRI or Kubernetes.

## Bring up the new cluster

1. Verify the bare-metal drive, physical NIC, firmware, bridge, maintenance
   and final control-plane addresses, DNS, NTP and Talos API from the physical
   LAN. Check the generated disk selector, versions and schematic. Bootstrap
   only the Talos node and Kubernetes API using the
   [Talos bootstrap guide](../architecture/talos-bootstrap.md). Keep Argo and
   data writers stopped. A maintenance boot can load the ZFS kernel module
   when it sees disk signatures. The extension service waits for CRI. Before
   sending a complete configuration, `task talos:apply` preseeds an
   `ExtensionServiceConfig` named `zfs-service` with
   `ZPOOL_IMPORT_PATH=/dev/null` and checks its rendered status in
   maintenance. Supply the approved `DEBUG_IMAGE` for its authenticated
   host checks. Keep this discovery restriction active for pool inspection.
   The unrestricted service attempts a forced import of every visible pool,
   including pools whose filesystems cannot be mounted.
2. Perform the mount and ACL procedure below. Meet the identity, reboot and
   copy prerequisites before launching the storage foundation.

### Mount the surviving datasets

From the Mac, start one privileged debug shell on the physical node. Set
`DEBUG_IMAGE` to an approved Linux image with util-linux `nsenter`, or use a
local image tarball for offline bootstrap. The release Talos CLI starts the
container with host PID visibility and a separate mount namespace. Run the
host ZFS binaries in PID 1's mount namespace and root:

```sh
talosctl -n "$NODE" debug --namespace inmem "$DEBUG_IMAGE" --args /bin/sh
```

```sh
host() { nsenter --mount=/proc/1/ns/mnt --root=/proc/1/root -- "$@"; }
zpool() { host /usr/local/sbin/zpool "$@"; }
zfs() { host /usr/local/sbin/zfs "$@"; }
zpool list -Hp -o name,guid,health
```

Require an empty pool list. Set `P1` through `P4` to the four verified
`/dev/disk/by-partuuid/…` paths of the original ZFS member partitions.
Match the partition and parent-disk identities to preflight. Check the
available pool GUID against `data_guid` before importing it read-only.

```sh
candidates() { zpool import -d "$P1" -d "$P2" -d "$P3" -d "$P4" "$@"; }
candidates
candidates -N -o readonly=on -o cachefile=none "$DATA_GUID"
zpool get -Hp -o property,value guid,readonly,cachefile,altroot dpool
zpool status -LP dpool
zfs get -Hpr -t filesystem -o name,property,value,source mountpoint,canmount,mounted,readonly,sharenfs,sharesmb dpool
zfs get -Hp -o value guid "dpool/migration/appdata@$MIGRATION_SNAPSHOT"
zfs holds "dpool/migration/appdata@$MIGRATION_SNAPSHOT"
```

Verify four healthy members, the held snapshot GUID and the absence of
mounted datasets. Save the output off-node. Investigate any request to
force import, missing member, encryption lock or unknown feature. After
accepting the read-only inspection, run `zpool export dpool`, confirm an
empty pool list and use `candidates -N -o cachefile=none "$DATA_GUID"`
for the writable import. Keep automatic discovery restricted.

Save the displayed property table privately **before changing anything**.
The source's original table and import prefix are also in `preflight.json`.
With workloads fenced, plan only the datasets that need mounting. Keep
unneeded datasets, including TrueNAS system datasets with special or legacy
mountpoints, offline if they conflict with Talos. Record each such change
by name and property. For example, `zfs set canmount=noauto DATASET` prevents
an automatic mount; cleanly unmount it separately if currently mounted.
Keep share properties disabled on the target. Check the host mount table
and underlying target directories for existing data before remapping.

On the recorded source the root mountpoint is default, media, Restic and
migration inherit from the root, and staged appdata inherits from migration.
TrueNAS imported the pool with a temporary `/mnt` altroot. The original
default resolves to `/dpool` on Talos. Verify this layout and confirm the
target directories are absent or empty. Record the root property value and
source off-node, then set the single root override without mounting anything.

```sh
zfs set -u mountpoint=/var/mnt/dpool dpool
zfs get -Hr -t filesystem -o name,property,value,source mountpoint,canmount dpool
```

Verify the resulting inherited paths, the legacy TrueNAS system mounts and
`mountpoint=none` on the OpenEBS parent. Review any unexpected child override
before mounting. Use `zfs mount DATASET` on the verified root, media, Restic,
migration and migration/appdata filesystems in that order. Check each source
and filesystem type in `/proc/1/mountinfo`, the read-only stage and its
snapshot GUID. Keep the home and dump datasets unmounted for inspection.

### Create the OpenEBS parent

If Phase 1 created `dpool/k8s`, check its recorded GUID and properties and
verify it has no children before first provisioning. Leave its mountpoint
at `none`. For a deferred creation, use the following procedure.

On the same verified pool, check `zfs list -H -o name -r dpool` before
creating the new parent. Use a new empty `dpool/k8s` with POSIX ACLs and
extended attributes for app PVCs. Keep each existing shared dataset's ACL
model intact. For case-sensitive source appdata and a Linux target:

```sh
zfs create -o mountpoint=none -o acltype=posixacl -o xattr=sa -o sharenfs=off -o sharesmb=off dpool/k8s
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

With all writers still held, clear `TALOS_MAINTENANCE_NODE` and export
`MIGRATION_POOL_GUID`, `MIGRATION_SNAPSHOT` and `MIGRATION_SNAPSHOT_GUID`
from the private source receipts. Run
`TALOS_ZFS_RELEASE_CONFIRM="$MIGRATION_POOL_GUID" task talos:release-zfs`.
It stages discovery limited to the four member partition UUIDs for the next
boot. Match those four paths to preflight. Confirm durable UEFI boot order,
then reboot with `talosctl -n "$NODE" reboot`. Verify the importer scope,
the original pool GUID, all four members online, the expected mounts and
the held stage snapshot after reboot. In the isolated rehearsal, verify that an absent pool or
an ordinary directory at either local mount stops writers. To recover from
a missing-pool boot, verify the GUID and import/mount the original pool first.
Wait for the CSI node to become Ready. Recreate blocked static-volume Pods
so kubelet rebinds the recovered filesystems. Check their init-container
results before resuming writers.

### Restore and hand off

1. **Install the held foundation.** Confirm the source is fenced and the
   cutover PR is merged. Use a clean checkout of the resulting `master`.
   Keep the physical Talos inputs from the [bootstrap guide](../architecture/talos-bootstrap.md)
   in the environment. Set the old repository's decrypted ID and its existing
   password in the [Restic secret inputs](restic-backup-restore.md). Use the
   private evidence produced by the source tasks.

   ```sh
   evidence="$(dirname "$MIGRATION_CONFIG")"
   export MIGRATION_POOL_GUID="$(jq -er .pool_guid "$evidence/stage.json")"
   export MIGRATION_SNAPSHOT="$(jq -er .snapshot "$MIGRATION_CONFIG")"
   export MIGRATION_SNAPSHOT_GUID="$(jq -er .snapshot_guid "$evidence/stage.json")"
   task platform:foundation
   ```

2. **Seed and compare the appdata.** The copy Jobs provision on the physical
   node, check the mount sources, preserve numeric owners, POSIX ACLs, xattrs
   and hardlinks, then compare content and metadata. Verification mounts each
   target read-only and computes another comparison against the snapshot.
   Keep the completed Jobs as receipts. If a copy Job exhausts its retries,
   inspect its logs and resolve the cause. Delete only that failed Job and
   retry using the original PVC, UID, and held snapshot.

   ```sh
   MIGRATION_CONFIRM=restore task migration:restore
   task migration:verify
   ```

3. **Authorize application startup.** Check claim bindings and capacities,
   source ACL evidence and the private Restic snapshot list. Record the
   cluster configuration/volume mapping off-node. Release application writers
   with `PLATFORM_HANDOFF_CONFIRM=true task platform:handoff`. The handoff
   repeats verification and records an immutable marker before starting Argo.

4. **Accept the applications.** Check the API and LAN DNS, Jellyfin's
   read-only library and playback, hardlinks across download/import paths,
   qBittorrent's VPN, Home Assistant/Scrypted discovery, Paperless document
   retrieval, Karakeep assets, and SparkyFitness's native database and uploads.
   Test one restore into scratch storage and a workstation Restic backup.
   Verify backup coverage in all three namespaces. Initialize and inspect
   the storage maintenance Jobs and their Gatus check. Test one cold boot
   with workloads held, then verify production services and the pool identity.
   Shared file access from outside Kubernetes requires a separately selected
   service; the former SMB/NFS shares retire at this cutover.

5. **Authorize the off-site copy.** Restore a known snapshot through the
   existing B2 crypt configuration and compare the file hash. Enable the
   target mirror using the snapshot-ID approval in the [Restic runbook](restic-backup-restore.md).
   Keep TrueNAS schedules and clients fenced until the corresponding target
   jobs succeed. Keep the held snapshots and all three SSD recovery pieces
   until you accept the cutover.

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
3. Gracefully shut down the bare-metal node. Put the SSD on the Mac, or boot
   the verified rescue USB with the SSD installed. If the HDDs stay
   attached, repeat the rescue identity and read-only fencing checks on this
   boot before opening the SSD for writing. In either case,
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
- [Current storage definitions](../../../apps/kube-system/zfs-localpv/values.yaml) and [Restic service configuration](../../../apps/selfhosted/restic/values.yaml)
- [TrueNAS configuration recovery](https://www.truenas.com/docs/scale/25.10/scaletutorials/systemsettings/advanced/managesysconfig/) explains the password secret seed.
- [TrueNAS pool management](https://www.truenas.com/docs/scale/25.10/scaletutorials/storage/managepoolsscale/) documents the export and configuration removal options.
- [TrueNAS cloud encryption](https://www.truenas.com/docs/scale/25.10/scaleuireference/dataprotection/cloudsynctasksscreensscale/) describes remote encryption and filename settings.
- [OpenZFS send](https://openzfs.github.io/openzfs-docs/man/master/8/zfs-send.8.html) documents snapshot streams and property replication.
- [OpenZFS pool import](https://openzfs.github.io/openzfs-docs/man/master/8/zpool-import.8.html) documents individual device selection, read-only imports and mounting controls.
- [SystemRescue boot options](https://www.system-rescue.org/manual/Booting_SystemRescue/) documents RAM boot and disabling automatic storage activation.
- [efibootmgr](https://manpages.debian.org/trixie/efibootmgr/efibootmgr.8.en.html) documents one-time UEFI boot selection and creating entries without changing the boot order.
- [Talos privileged debug implementation](https://github.com/siderolabs/talos/blob/v1.14.6/internal/app/debug/debug.go) documents host PID access in the release debugging profile.
- [Talos ZFS extension](https://github.com/siderolabs/extensions/tree/main/storage/zfs) documents import behavior and compatible mount paths.

## Related pages

- [Talos and platform bootstrap](../architecture/talos-bootstrap.md)
- [Storage and shared media](../architecture/storage.md)
- [Backup and recovery](../architecture/backup-recovery.md)
- [Restic restore procedure](restic-backup-restore.md)
