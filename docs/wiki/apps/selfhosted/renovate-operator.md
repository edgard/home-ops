# Renovate Operator

Purpose: Renovate Operator runs repository dependency-update jobs.
Status: current. Reviewed against: `74d60b4e0a7607351ba07234d24cd435cfd45f54`.

## Dependencies

Its raw RenovateJob and ExternalSecret link the operator to this Git repository.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

Review generated PR behavior and credentials after changing job or operator configuration.

The [repository Renovate configuration](../../../../.renovaterc.json5) combines
built-in managers for Actions, Ansible requirements, Terraform, and Kubernetes
images with custom extraction for app charts, images, upgrade targets, CI tools,
Gateway API, the Restic restore image, and the shared SecretSpec compatibility
pin in [`.secretspec-version`](../../../../.secretspec-version). When moving a dependency file, check
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

CI Python updates remain within the pinned Ansible core release's supported
control-node runtime range. Keep the toolchain's interpreter aligned with the
Taskfile default, and review the Python limit when upgrading Ansible core.
The [Ansible support matrix](https://docs.ansible.com/projects/ansible-core/devel/reference_appendices/release_and_maintenance.html#ansible-core-support-matrix)
defines the upstream compatibility boundary.

## Sources

- [Repository Renovate configuration](../../../../.renovaterc.json5)
- [CI toolchain](../../../../.github/actions/setup-toolchain/action.yml)
- [Taskfile interpreter default](../../../../Taskfile.yaml)
- [Operator tool defaults](../../../../ansible/roles/operator_secrets/defaults/main.yml)
- [App metadata](../../../../apps/selfhosted/renovate-operator/app.yaml)
- [Helm values](../../../../apps/selfhosted/renovate-operator/values.yaml)
- [Raw manifests](../../../../apps/selfhosted/renovate-operator/manifests)
- [Local extraction dry runs](https://docs.renovatebot.com/modules/platform/local/) explain how to check dependency discovery without creating branches.

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Talos installer contract](../../decisions/talos-image-factory.md)
- [Validation](../../architecture/validation.md)
