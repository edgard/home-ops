# Preserve the Talos Image Factory installer

Purpose: record the upgrade image constraint for the single node.
Status: current. Reviewed against: `d80872c8700249ef67aa42919e297c37e75faef3`.

[PR #394](https://github.com/edgard/home-ops/pull/394) corrected the Talos
upgrade path to use the installer specified by the committed machine
configuration, preserving the guest agent on the former VM. The physical
host's committed schematic includes the OpenZFS tooling, AMD microcode and
Realtek firmware. Submit the schematic to the Factory with this command and
compare the returned ID with the role defaults and control-plane patch.

```sh
curl --fail-with-body --silent --show-error \
  --header 'Content-Type: application/yaml' \
  --data-binary @ansible/roles/talos/files/metal-schematic.yaml \
  https://factory.talos.dev/schematics
```

Use the matching Factory `image/<id>/<version>/metal-amd64.raw.zst` artifact
when flashing the detached boot SSD. Use the `metal-installer/<id>:<version>`
image from the same schematic for installation and future upgrades. The
generation check verifies that the role and machine patch select the same
installer. The [migration runbook](../operations/truenas-migration.md) covers
source backups and the physical handoff.

Renovate's Ansible manager reads the image from the bootstrap patch. The
package lookup override reads upstream installer tags while preserving the
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
