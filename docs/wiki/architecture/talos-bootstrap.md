# Talos and platform bootstrap

Purpose: locate the cluster creation and upgrade boundaries.
Status: current. Reviewed against: `d9a1261970b4d6607056507421a71ad52b5d07ce`.

The Taskfile invokes Ansible for Talos configuration, bootstrap, upgrades, and
platform installation. SecretSpec resolves cloud material before node mutation.
Generation derives explicit Talos, Kubernetes, and installer targets from the
repository, validates output, restricts configured client paths, and cleans
temporary secrets. Platform bootstrap preserves storage, networking, image
warmup, and cert-manager ordering, then waits for ESO CRDs, SDK, controller, and
store readiness before Argo access/root handoff. The handoff verifies the merged
revision and ApplicationSet children within 300 seconds and fresh application
secrets within 600 seconds. See the [migration runbook](../operations/secrets-maintenance.md)
for external prerequisites and the limits of disposable versus production tests.

The [Image Factory installer decision](../decisions/talos-image-factory.md)
explains why upgrades must preserve the configured installer and its extensions.
An upgrade requires current node and snapshot preflight; this page does not
assert that the live node matches the repo.

## Sources

- [Operator secret contract](../../../secretspec.toml)
- [Maintenance runbook](../operations/secrets-maintenance.md)

- [Talos role defaults](../../../ansible/roles/talos/defaults/main.yml)
- [Talos generation tasks](../../../ansible/roles/talos/tasks/generate.yml)
- [Talos upgrade tasks](../../../ansible/roles/talos/tasks/upgrade.yml)
- [Platform bootstrap tasks](../../../ansible/roles/platform/tasks/bootstrap.yml)
- [Operator tasks](../../../Taskfile.yaml)

## Related pages

- [GitOps delivery](gitops-delivery.md)
- [Backup and recovery](backup-recovery.md)
- [Secrets](secrets.md)
