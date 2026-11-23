# Talos and platform bootstrap

Purpose: identify the physical node, rebuild its control plane and admit the correct storage before starting workloads.
Status: current. Reviewed against: `b898924ceaf8be0a1b00e20fed8f57369259f669` and this revision.

## Identify the node

Retain the cluster's Bitwarden Talos identity, a current etcd snapshot, the boot
SSD's whole-disk by-id path and serial, and the Ethernet port's permanent MAC.
Also keep the numeric `dpool` GUID and the four data partition UUIDs in the
operator's recovery inventory. On an enrolled cluster the pool GUID is in
`kube-system/storage-identity` and the authenticated Talos resource
`extensionserviceconfigs zfs-service` gives the four approved by-partuuid paths.
Record replacement disks when their identities change. The
[storage architecture](storage.md) defines the required physical pool, dataset
properties and media and backup repository layout.

Use the [Image Factory installer](../decisions/talos-image-factory.md) on
the target SSD. Set `TALOS_NODE` to the final reserved address,
`TALOS_INSTALL_DISK` to the SSD's whole-disk by-id path,
`TALOS_INSTALL_SERIAL` to its serial and `TALOS_UPLINK_MAC` to the
physical port's permanent MAC. The generated configuration names the node
`homelab`, binds the port to `br0` and preserves the bridge's DHCP reservation.
The Talos installation selector requires the selected serial and by-id path,
with wiping disabled. When Talos omits the SSD serial, also set
`TALOS_INSTALL_WWID` to its independently recorded NAA identifier. The role
checks the live WWID, the serial suffix on the exact ATA by-id and any serial
the kernel does report. Regenerate the machine configuration with these inputs
when replacing the boot device.

For a new node, set `TALOS_MAINTENANCE_NODE` to the physical NIC's initial
DHCP address. Set `TALOS_MAINTENANCE_FINGERPRINT` to the padded base64 SHA-256
public-key fingerprint from the trusted physical console or first-contact
record. Each maintenance read and configuration submission then verifies the
same key. The final endpoint uses authenticated Talos credentials. Every apply
checks the system disk and NIC before submitting configuration. Platform
operations also match the Kubernetes node's hardware UUID and InternalIP
against that endpoint.

## CPU power preference

The [control-plane patch](../../../ansible/roles/talos/files/controlplane-patch.yaml)
sets the Ryzen 9 3900X's energy performance preference to `balance_power`.
The active `amd-pstate-epp` driver chooses frequencies under load and can
still boost. The patch names each of the 24 CPU frequency policies on this
node. On replacement hardware, check the available policies and supported
preferences before reusing the patch.

Read the current preference and available choices through the Talos API:

```sh
talosctl -e "$TALOS_NODE" -n "$TALOS_NODE" read /sys/devices/system/cpu/cpufreq/policy0/energy_performance_preference
talosctl -e "$TALOS_NODE" -n "$TALOS_NODE" read /sys/devices/system/cpu/cpufreq/policy0/energy_performance_available_preferences
```

To restore the previous policy, set the same EPP keys to
`balance_performance` in both the tracked patch and the live configuration.
A targeted `talosctl patch mc --mode=no-reboot` accepts the SysfsConfig
document on this Talos version. Use `--dry-run` before applying it and read
back the preference across the policies afterward.

## First boot and pool enrollment

The four data HDDs can stay attached. Set `DEBUG_IMAGE` to a trusted Linux
debug image or local archive with a shell, util-linux `nsenter` and standard
coreutils. Host administration uses `talosctl debug --namespace inmem`.
`task talos:gen` generates the machine and client configuration.
`task talos:apply` first sends the standalone `zfs-service` setting
`ZPOOL_IMPORT_PATH=/dev/null`, checks its rendered status while Talos is
still in maintenance, then applies the control plane with that restriction.
At the final authenticated address it verifies the setting, loads the explicit
ZFS kernel module and confirms the running extension imported no pool.
Clear both maintenance variables after this transition. If the bridge changed
addresses before an interruption, rerun at the final address.

`task cluster:create` generates and applies this configuration and bootstraps
fresh etcd. It pauses before platform installation while pool discovery is
disabled. For an interrupted fresh bootstrap, `task talos:bootstrap` checks
the local etcd member's health, voting status and advertised endpoints before
issuing kubeconfig. For recovery of existing PVC bindings, follow the
[etcd recovery procedure](#recover-the-existing-control-plane) before running
either fresh bootstrap command.

To enroll storage, export the independently recorded `ZFS_POOL_GUID` and
`ZFS_MEMBER_PARTUUIDS`. The latter is a space-separated list of four lowercase
GPT partition UUIDs. After confirming exclusive ownership of the pool, run
the release task with its GUID.

```sh
TALOS_ZFS_RELEASE_CONFIRM="$ZFS_POOL_GUID" task talos:release-zfs
```

With discovery disabled, the task requires an empty imported-pool list.
It limits discovery to the four partitions and imports the numeric GUID
read-only, with mounting and cache-file updates disabled. It checks that the four online leaves
are partitions on different disks, all separate from the system SSD, verifies
the permanent dataset properties and exports the pool. If OpenZFS requires a
forced import, first establish exclusive ownership and recover a cleanly
exported pool before retrying this task.

The task stages the four verified partition paths for the next planned reboot.
After reboot, `task platform:foundation` checks the active policy, physical
pool, member identities and live dataset mounts before installing CSI. On its
first enrollment set `ZFS_POOL_GUID`; the immutable `kube-system/storage-identity`
records the expected GUID and system SSD by-id for subsequent checks. See
[storage architecture](storage.md) for the restore and GitOps release sequence.

## Recover the existing control plane

On the healthy node, use the authenticated Talos client to save an etcd
snapshot to a new filename in an owner-only, encrypted directory off-node.
Keep its reported revision, key count and hash together with the matching
Talos identity, component versions and PVC-to-dataset inventory.

```sh
umask 077
talosctl -e "$TALOS_NODE" -n "$TALOS_NODE" etcd snapshot "$SNAPSHOT"
```

1. Power off the former node. On the replacement boot SSD, generate and
   apply the matching configuration with `task talos:gen` and
   `task talos:apply`. Verify that the discovery restriction is active and
   no pool is imported. Keep that restriction across the etcd restore.
   Isolate the recovery network from application clients, external services
   and remote backup destinations. Permit operator access and the infrastructure
   required to bring up the control plane. A restored Pod can already have a
   node assignment and can start as soon as the API returns.
2. Check `talosctl -e "$TALOS_NODE" -n "$TALOS_NODE" service etcd`. When
   the verified node's service is in `Preparing`, recover the snapshot with
   its built-in hash check. Confirm the recovered revision and key count
   match the backup and the single voting member is healthy.

   ```sh
   talosctl -e "$TALOS_NODE" -n "$TALOS_NODE" bootstrap --recover-from="$SNAPSHOT"
   talosctl -e "$TALOS_NODE" -n "$TALOS_NODE" etcd members
   talosctl -e "$TALOS_NODE" -n "$TALOS_NODE" etcd status
   ```

3. Use the matching kubeconfig against this node. Before releasing the pool,
   record the restored workload state, scale the Argo CD application and
   ApplicationSet controllers to zero, suspend backup and maintenance CronJobs,
   stop their active Jobs, and scale all application writers to zero. Verify
   that their Pods have terminated, including existing Pods bound to the node.
4. Compare the recovered PVC UIDs, PV claim references and CSI handles, and
   OpenEBS ZFSVolumes against the off-node inventory. If the replacement SSD
   has a new by-id, save the old immutable `kube-system/storage-identity`.
   Independently verify the new SSD and the retained pool GUID and four member
   partitions. Recreate the ConfigMap with the updated system disk while
   controllers and workloads remain fenced.
5. Enroll the verified pool, reboot and check its native dataset GUIDs, live
   mounts, storage identity and bindings against the inventory. Restore the
   saved replica counts and schedules, GitOps reconciliation and client access
   after those checks. For missing control-plane state, use the
   [fresh-claim recovery procedure](../operations/restic-backup-restore.md#new-cluster-or-lost-etcd-state).

The upstream guide covers the service states, snapshot integrity and official
recovery command. [Talos 1.14 disaster recovery](https://docs.siderolabs.com/talos/v1.14/build-and-extend-talos/cluster-operations-and-maintenance/disaster-recovery)

## Routine operation

Ordinary `task talos:apply` preserves the active discovery policy and stops
if a different machine configuration is already staged. A member replacement
changes its partition UUID. Once the pool is healthy and resilvering has
finished, update the recovery inventory and run the same explicit release
with the new four UUIDs. On an enrolled node the task verifies the mounted
pool in place and stages the changed paths for a planned reboot. Repeating
release with the existing paths verifies the pool without staging another
configuration.

Take a restricted etcd snapshot before a live Talos upgrade. The upgrade
checks physical and Kubernetes identity, pool membership and the mounted
datasets, then drains the single node and keeps it cordoned through reboot.
The role releases the cordon after verifying the new server version and the
returned storage. The workload PID and mount namespaces in Talos 1.14 remain
isolated. OpenEBS and maintenance Pods use explicit host mounts and the host's
ZFS extension tools.

Tuppr handles ordinary Kubernetes upgrades when Argo applies the committed
target. For a manual upgrade, follow the [Tuppr suspension procedure](../apps/platform-system/tuppr.md#operational-note).

Platform foundation renders the [Envoy Gateway CRD chart](../apps/platform-system/envoy-gateway-crds.md)
from the GitOps pin and values. It verifies HTTPRoute discovery before installing Argo CD. Its private Restic service opens the
existing repository and checks its ID and snapshot listing. See
[operator credential maintenance](../operations/secrets-maintenance.md)
for its external credentials. Platform removal forwards its timeout through
the Kubernetes collection's Helm `wait_timeout` parameter.

## Sources

- [Operator tasks](../../../Taskfile.yaml) and [CLI secret contract](../../../secretspec.toml)
- [Talos defaults](../../../ansible/roles/talos/defaults/main.yml) and [machine configuration generation](../../../ansible/roles/talos/tasks/generate.yml)
- [Physical target checks](../../../ansible/roles/talos/tasks/target.yml)
- [First-boot ZFS restriction](../../../ansible/roles/talos/tasks/preseed_zfs.yml) and [four-member release](../../../ansible/roles/talos/tasks/release_zfs.yml)
- [Storage admission](../../../ansible/roles/platform/tasks/storage_mounts.yml) and [Talos upgrades](../../../ansible/roles/talos/tasks/upgrade.yml)
- [Platform bootstrap](../../../ansible/roles/platform/tasks/bootstrap.yml) and [GitOps release](../../../ansible/roles/platform/tasks/release_root.yml)

## Related pages

- [GitOps delivery](gitops-delivery.md)
- [Backup and recovery](backup-recovery.md)
- [Secrets](secrets.md)
