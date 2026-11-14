# Preserve the Talos Image Factory installer

Purpose: record the upgrade image constraint for the single node.
Status: current. Reviewed against: `62ac80dd843b2975b122c9cdf9fd1c1cf67bc060`.

[PR #394](https://github.com/edgard/home-ops/pull/394) corrected the Talos
upgrade path to use the installer specified by the committed machine
configuration. The generic installer would omit the QEMU guest agent extension.
Repository policy checks target compatibility and alignment with the machine
install image. The upgrade role constructs the command from that image; command simulations
are retired. Before a live upgrade, confirm the node's current install image and
take a restricted etcd snapshot; the wiki cannot establish current node state.

Renovate's Ansible manager reads the image from the bootstrap patch. The
package lookup override reads upstream installer tags while preserving the
factory schematic path in the patch. The annotated version in the role
defaults is tracked separately through the custom regex manager. Moving
either input requires updating its manager's file pattern. Repository
validation rejects a version mismatch between those inputs.

## Sources

- [Talos upgrade change, PR #394](https://github.com/edgard/home-ops/pull/394)
- [Talos role defaults](../../../ansible/roles/talos/defaults/main.yml)
- [Control-plane patch](../../../ansible/roles/talos/files/controlplane-patch.yaml)
- [Target compatibility checks](../../../validation/test_repository.py)
- [Upgrade runtime guards](../../../ansible/roles/talos/tasks/upgrade.yml)
- [Renovate configuration](../../../.renovaterc.json5)

## Related pages

- [Talos bootstrap](../architecture/talos-bootstrap.md)
- [Backup and recovery](../architecture/backup-recovery.md)
- [Renovate Operator](../apps/selfhosted/renovate-operator.md)
