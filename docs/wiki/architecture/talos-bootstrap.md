# Talos and platform bootstrap

Purpose: locate the cluster creation and upgrade boundaries.
Status: current. Reviewed against: `ae198e1dcee21682caa39016c64839a7e52a416c`.

The Taskfile invokes Ansible for Talos configuration, bootstrap, upgrades, and
platform installation. SecretSpec resolves cloud material before node mutation.
Generation derives explicit Talos, Kubernetes, and installer targets from the
repository, validates output, restricts configured client paths, and cleans
temporary secrets. Platform bootstrap preserves storage, networking, image
warmup, and cert-manager ordering, then waits for ESO CRDs, SDK, controller, and
store readiness before Argo access/root handoff. The handoff verifies the merged
revision and ApplicationSet children within 300 seconds and fresh application
secrets within 600 seconds. See the [maintenance and recovery runbook](../operations/secrets-maintenance.md)
for external prerequisites and the limits of disposable versus production tests.

The [Image Factory installer decision](../decisions/talos-image-factory.md)
explains why upgrades must preserve the configured installer and its extensions.
An upgrade requires current node and snapshot preflight; this page does not
assert that the live node matches the repo.
The upgrade role reads the selected server's JSON version response and requires
its tag to equal the configured installer version. A matching local client
version cannot satisfy this check.

Platform preflight keeps the GitHub identity endpoint in the nonsecret
`platform_repository_identity_url` role default. Isolated tests point that HTTP
boundary at loopback while exercising the real URI module. CLI commands
continue to use the existing GitHub endpoint.

Platform removal forwards `platform_helm_timeout` through `wait_timeout`: the
pinned Kubernetes collection's uninstall path does not forward its preferred
`timeout` parameter. The native CLI fixture checks both configured timeout and
failure propagation, including future collection updates.

## Sources

- [CLI secret contract](../../../secretspec.toml)
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
