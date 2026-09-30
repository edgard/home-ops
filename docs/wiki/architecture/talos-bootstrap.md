# Talos and platform bootstrap

Purpose: locate the cluster creation and upgrade boundaries.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

The Taskfile invokes Ansible for Talos configuration, bootstrap, upgrades, and
platform installation. Talos bootstrap secrets live in the committed encrypted
Vault file; local operator credentials stay outside Git. Platform bootstrap
installs storage and networking prerequisites, then cert-manager, External
Secrets, and Argo CD before normal GitOps reconciliation.

The [Image Factory installer decision](../decisions/talos-image-factory.md)
explains why upgrades must preserve the configured installer and its extensions.
An upgrade requires current node and snapshot preflight; this page does not
assert that the live node matches the repo.

## Sources

- [Talos role defaults](../../../ansible/roles/talos/defaults/main.yml)
- [Talos generation tasks](../../../ansible/roles/talos/tasks/generate.yml)
- [Talos upgrade tasks](../../../ansible/roles/talos/tasks/upgrade.yml)
- [Platform bootstrap tasks](../../../ansible/roles/platform/tasks/bootstrap.yml)
- [Operator tasks](../../../Taskfile.yaml)

## Related pages

- [GitOps delivery](gitops-delivery.md)
- [Backup and recovery](backup-recovery.md)
- [Secrets](secrets.md)
