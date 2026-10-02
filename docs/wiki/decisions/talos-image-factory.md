# Preserve the Talos Image Factory installer

Purpose: record the upgrade image constraint for the single node.
Status: current. Reviewed against: `9b6b7afd758013ef4288ed68b10f088053661e07`.

[PR #394](https://github.com/edgard/home-ops/pull/394) corrected the Talos
upgrade path to use the installer specified by the committed machine
configuration. The generic installer would omit the QEMU guest agent extension.
The upgrade contract compares the default command with the machine install
image. Before a live upgrade, confirm the node's current install image and
take a restricted etcd snapshot; the wiki cannot establish current node state.

Renovate must discover both the bootstrap patch and the upgrade target in
`ansible/roles/talos/defaults/main.yml`. Moving a role input requires updating
the corresponding manager file pattern. The upgrade contract rejects a version
mismatch rather than allowing the default command to target an older installer.

## Sources

- [Talos upgrade change, PR #394](https://github.com/edgard/home-ops/pull/394)
- [Talos role defaults](../../../ansible/roles/talos/defaults/main.yml)
- [Control-plane patch](../../../ansible/roles/talos/files/controlplane-patch.yaml)
- [Upgrade contract](../../../ansible/tests/talos-upgrade.yml)
- [Renovate configuration](../../../.renovaterc.json5)

## Related pages

- [Talos bootstrap](../architecture/talos-bootstrap.md)
- [Backup and recovery](../architecture/backup-recovery.md)
- [Renovate Operator](../apps/selfhosted/renovate-operator.md)
