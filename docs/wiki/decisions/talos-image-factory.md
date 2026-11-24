# Preserve the Talos Image Factory installer

Purpose: record the upgrade image constraint for the single node.
Status: current. Reviewed against: `46c0ab2a` and this revision.

[PR #394](https://github.com/edgard/home-ops/pull/394) corrected the Talos
upgrade path to use the installer specified by the committed machine
configuration. The bare-metal schematic includes the OpenZFS tooling, AMD microcode and
Realtek firmware. Submit the schematic to the Factory with this command and
compare the returned ID with the control-plane patch and live installer image.

```sh
curl --fail-with-body --silent --show-error \
  --header 'Content-Type: application/yaml' \
  --data-binary @ansible/roles/talos/files/metal-schematic.yaml \
  https://factory.talos.dev/schematics
```

For a disk-image installation, use the Factory artifact
`image/<id>/<version>/metal-amd64.raw.zst` for the verified system SSD.
Select the `metal-installer/<id>:<version>` image from the same schematic
for the machine configuration and upgrades. Tuppr preserves the node's Factory
installer path and schematic when changing the version. Generation verifies
that the bootstrap image tag matches the TalosUpgrade target. The [Talos bootstrap procedure](../architecture/talos-bootstrap.md)
describes disk identification, network setup and pool enrollment.

Renovate's Ansible manager reads the image from the bootstrap patch. The
package lookup uses stable `ghcr.io/siderolabs/installer-base` tags published
with [Talos releases](https://github.com/siderolabs/talos/releases/tag/v1.14.6), preserving the
factory schematic path in the patch. The custom regex manager reads the
annotated TalosUpgrade version. Both dependencies share a Talos release PR,
including patch updates; patches and minors automerge after CI, while major
and rollback updates require review. Moving either input requires updating its
manager's file pattern. Repository validation and generation reject a version
mismatch between those inputs.

## Sources

- [Talos upgrade change, PR #394](https://github.com/edgard/home-ops/pull/394)
- [Committed physical schematic](../../../ansible/roles/talos/files/metal-schematic.yaml)
- [Talos upgrade target](../../../apps/platform-system/tuppr/manifests/tuppr-talos.talosupgrade.yaml)
- [Control-plane patch](../../../ansible/roles/talos/files/controlplane-patch.yaml)
- [Target compatibility checks](../../../validation/test_repository.py)
- [Generation target checks](../../../ansible/roles/talos/tasks/validate_generation.yml)
- [Native installer resolution](https://github.com/home-operations/tuppr/blob/0.5.14/docs/src/content/docs/talos-upgrades.md#how-the-upgrade-image-is-resolved) explains preserving the node's configured image and extensions.
- [Renovate configuration](../../../.renovaterc.json5)

## Related pages

- [Talos bootstrap](../architecture/talos-bootstrap.md)
- [Backup and recovery](../architecture/backup-recovery.md)
- [Renovate Operator](../apps/selfhosted/renovate-operator.md)
