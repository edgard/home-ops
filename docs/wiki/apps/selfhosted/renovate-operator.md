# Renovate Operator

Purpose: Renovate Operator runs repository dependency-update jobs.
Status: current. Reviewed against: `9f966763020631cd9bab2de5ddd8471434b71876`.

## Dependencies

Its raw RenovateJob and ExternalSecret link the operator to this Git repository.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

Review generated PR behavior and credentials after changing job or operator configuration.

The [repository Renovate configuration](../../../../.renovaterc.json5) combines
built-in managers for Actions, Python project metadata/uv locks, Ansible
collections, Terraform/provider locks, and Kubernetes
images with custom extraction for app charts, images, upgrade targets, CI tools,
Gateway API, the Restic restore image, and the shared SecretSpec compatibility
pin in [the CLI role defaults](../../../../ansible/roles/cli_secrets/defaults/main.yml). When moving a dependency file, check
its manager file patterns and run a local extraction dry run; valid configuration
alone does not prove that the dependency is still discovered.

Talos updates cover both the machine-config installer and the upgrade target in
role defaults. The [installer contract](../../decisions/talos-image-factory.md)
keeps these aligned. Gateway API upgrades require manual review and refresh the
vendored CRDs through the configured post-upgrade command; the RenovateJob allows
that command. Major updates also require manual review. Release-age and version
limits remain in the repository configuration.

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
- [Local extraction dry runs](https://docs.renovatebot.com/modules/platform/local/) explain how to check dependency discovery without creating branches.

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Talos installer contract](../../decisions/talos-image-factory.md)
- [Validation](../../architecture/validation.md)
