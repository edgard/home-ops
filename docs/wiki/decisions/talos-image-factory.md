# Preserve the Talos Image Factory installer

Purpose: record the upgrade image constraint for the single node.
Status: current. Reviewed against: `e0ffdb032870a9272c7abd691788e9b4e4b48ee1` and this revision.

[PR #394](https://github.com/edgard/home-ops/pull/394) corrected the Talos
upgrade path to use the installer specified by the committed machine
configuration. The bare-metal schematic includes the OpenZFS tooling, AMD microcode and
Realtek firmware. Submit the schematic to the Factory with this command and
compare the returned ID with the role defaults and control-plane patch.

```sh
curl --fail-with-body --silent --show-error \
  --header 'Content-Type: application/yaml' \
  --data-binary @ansible/roles/talos/files/metal-schematic.yaml \
  https://factory.talos.dev/schematics
```

For a disk-image installation, use the Factory artifact
`image/<id>/<version>/metal-amd64.raw.zst` for the verified system SSD.
Select the `metal-installer/<id>:<version>` image from the same schematic
for the machine configuration and upgrades. Generation verifies that both
paths use the same installer. The [Talos bootstrap procedure](../architecture/talos-bootstrap.md)
describes disk identification, network setup and pool enrollment.

Renovate's Ansible manager reads the image from the bootstrap patch. The
package lookup uses stable `ghcr.io/siderolabs/installer-base` tags published
with [Talos releases](https://github.com/siderolabs/talos/releases/tag/v1.14.6), preserving the
factory schematic path in the patch. The annotated version in the role
defaults is tracked separately through the custom regex manager. Moving
either input requires updating its manager's file pattern. Repository
validation rejects a version mismatch between those inputs.

## Sources

- [Talos upgrade change, PR #394](https://github.com/edgard/home-ops/pull/394)
- [Committed physical schematic](../../../ansible/roles/talos/files/metal-schematic.yaml)
- [Talos role defaults](../../../ansible/roles/talos/defaults/main.yml)
- [Control-plane patch](../../../ansible/roles/talos/files/controlplane-patch.yaml)
- [Target compatibility checks](../../../validation/test_repository.py)
- [Upgrade runtime guards](../../../ansible/roles/talos/tasks/upgrade.yml)
- [Renovate configuration](../../../.renovaterc.json5)

## Related pages

- [Talos bootstrap](../architecture/talos-bootstrap.md)
- [Backup and recovery](../architecture/backup-recovery.md)
- [Renovate Operator](../apps/selfhosted/renovate-operator.md)
