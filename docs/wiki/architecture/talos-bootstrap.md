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

A [separate cold recovery entry point](../../../ansible/playbooks/platform-recovery.yml)
dispatches a bounded in-cluster Job under the shared maintenance Lease and a
durable source-bound journal before chart work. A real bound-token Pod executes
the mutations; retries require exact Job/Pod fencing and Ready-node/absence
barriers. It keeps root/ApplicationSet/consumer reconciliation held from first
creation while recovery infrastructure starts. Base scheduling, CNI, DNS, and
registry access must already work. Normal bootstrap refuses an unfinished cold
API journal before foundational mutations. Successful global admission must record its bound
completion before normal bootstrap is available again. The runtime admission
finalizer remains an activation blocker; see the [exact recovery boundary](../operations/shared-data.md#cold-infrastructure-recovery-and-admission-boundary).

Registered node and foundational platform mutations now use the shared
[NativeCLI operation exclusion](../operations/shared-data.md#registered-talos-and-platform-operation-exclusion).
The workstation keeps its existing credentials and commands, while the common
Lease/journal exclude data operations. Unknown native work remains held for
manual inspection and is never reclaimed through Pod fencing or Lease expiry.
Native operations durably fence Root, ApplicationSet and Tuppr reconciliation,
stop Tuppr and reject independent upgrade workers before mutation; ordinary app
writers remain running. Bootstrap creates Root already held, completes all
foundational mutation, restores Root last, then performs its read-only handoff.
Fresh pre-API creation needs explicit positive native disk/etcd evidence.
Platform removal requires already-adopted `Delete=false` retention on selfhosted
so cascading root deletion cannot erase the active Lease or journal; successful
standalone removal retains that namespace. See the linked runbook for the exact
proofs, finalizer fallback, and live acceptance boundary.

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
