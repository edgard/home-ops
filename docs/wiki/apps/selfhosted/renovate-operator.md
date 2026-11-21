# Renovate Operator

Purpose: Renovate Operator runs repository dependency-update jobs.
Status: current. Reviewed against: `bec6f23a0ad540fde038cdcdb7573473089102a0`.

## Dependencies

Its raw RenovateJob and ExternalSecret link the operator to this Git repository.
The chart renders its CRDs as regular manifests so Argo CD can discover the
RenovateJob definition in the same sync and apply it before the wave-1 job.
In the chart's default hook mode, first-sync validation can fail before the
hook runs. Argo CD now tracks the CRDs. Review proposed CRD pruning before
removing the app or changing modes, since deleting a CRD deletes its instances.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

Review generated PR behavior and credentials after changing job or operator configuration.

The [repository Renovate configuration](../../../../.renovaterc.json5) combines
built-in managers for Actions, Python project metadata/uv locks, Ansible
collections and the Talos bootstrap image, Terraform/provider locks, and
Kubernetes and Helm values images. The Actions manager also reads the uv,
Helm, and OpenTofu inputs in the CI toolchain.

Two custom managers read the Helm chart pins from ApplicationSet inputs and
the annotated versions and image tags elsewhere. Put a `# renovate:` comment
directly above the matching key for upgrade targets, remaining CI tool pins,
Gateway API, the Restic restore image, the storage inspection image, or the
runtime SecretSpec pin. When
moving a pin, check its manager's file patterns and compare the dependencies
reported by a local extraction dry run.

For a digest-pinned app-template image, put `tag@sha256:…` in `image.tag`.
The built-in Helm values manager reads both parts and updates them together.
A separate `image.digest` is invisible to that manager; a tag-only update then
leaves Kubernetes pulling the old digest.

Talos updates cover both the machine-config installer and the upgrade target in
role defaults. The [installer contract](../../decisions/talos-image-factory.md)
keeps these aligned. Gateway API upgrades require manual review and refresh the
vendored CRDs through the configured post-upgrade command; the RenovateJob allows
that command.

Routine dependency updates and scheduled lockfile refreshes are eligible for
automerge through the required [Quality Gate](../../architecture/validation.md).
Renovate creates lockfile maintenance on a separate branch. If another update
changes a shared lock first, Renovate regenerates the maintenance branch from the
updated base on a later run and CI checks the new result.

The PR gate also exercises the CI actions, their uv, Helm, and OpenTofu inputs,
and the allowlisted validation tools whose major updates are eligible for
automerge. Other majors require manual review because
rendering and offline checks leave deployed workloads, provider plans, and
operator procedures outside their coverage. Kubernetes and Talos release-line
changes and downgrades require review of live upgrade preconditions. Their
ordinary patches remain eligible for automerge within the version and release-age
limits in the repository configuration. When changing the Talos release line,
review its Kubernetes ceiling against the [Talos support matrix](https://docs.siderolabs.com/talos/v1.14/getting-started/support-matrix).

Gotenberg stays within the major supported by Paperless's bundled conversion
client. The [Paperless operational note](paperless.md) records the request-field
incompatibility and the acceptance check required before lifting that limit.

The OpenTofu `required_version` constraint is manually managed. Renovate excludes
the Terraform CLI dependency from both `.terraform-version` files and Terraform
configuration, while provider dependencies and the CI OpenTofu tool remain managed.

CI reads the supported Python range from project metadata; the Taskfile's
preferred interpreter must satisfy it. Renovate leaves this range manually
managed and continues updating Python packages and their uv lock. Review the
range with Ansible core upgrades. Provider updates use the OpenTofu registry,
and native lock maintenance refreshes Python transitive dependencies and maintains
provider selections within their constraints. Provider version PRs regenerate
their lock hashes. Verify extraction and artifact updates when changing these files.
The [Ansible support matrix](https://docs.ansible.com/projects/ansible-core/devel/reference_appendices/release_and_maintenance.html#ansible-core-support-matrix)
defines the upstream compatibility boundary.

## Sources

- [Repository Renovate configuration](../../../../.renovaterc.json5)
- [CI toolchain](../../../../.github/actions/setup-toolchain/action.yml)
- [Taskfile interpreter default](../../../../Taskfile.yaml)
- [Python project metadata](../../../../pyproject.toml)
- [Python lock](../../../../uv.lock)
- [Provider lock](../../../../terraform/.terraform.lock.hcl)
- [CLI tool defaults](../../../../ansible/roles/cli_secrets/defaults/main.yml)
- [App metadata](../../../../apps/selfhosted/renovate-operator/app.yaml)
- [Helm values](../../../../apps/selfhosted/renovate-operator/values.yaml)
- [Raw manifests](../../../../apps/selfhosted/renovate-operator/manifests)
- [Argo CD missing-resource dry runs](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-options/#skip-dry-run-for-new-custom-resources-types) explains first-sync handling when the CRD is in the same sync.
- [Local extraction dry runs](https://docs.renovatebot.com/modules/platform/local/) explain how to check dependency discovery without creating branches.
- [Renovate rebasing](https://docs.renovatebot.com/updating-rebasing/) explains how the bot regenerates branches after the base changes.

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Talos installer contract](../../decisions/talos-image-factory.md)
- [Validation](../../architecture/validation.md)
