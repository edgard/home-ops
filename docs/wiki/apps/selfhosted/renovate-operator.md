# Renovate Operator

Purpose: Renovate Operator runs repository dependency-update jobs.
Status: current. Reviewed against: `9b6b7afd758013ef4288ed68b10f088053661e07`.

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
Gateway API, and the Restic restore image. When moving a dependency file, check
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

## Sources

- [Repository Renovate configuration](../../../../.renovaterc.json5)
- [App metadata](../../../../apps/selfhosted/renovate-operator/app.yaml)
- [Helm values](../../../../apps/selfhosted/renovate-operator/values.yaml)
- [Raw manifests](../../../../apps/selfhosted/renovate-operator/manifests)
- [Local extraction dry runs](https://docs.renovatebot.com/modules/platform/local/) explain how to check dependency discovery without creating branches.

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Talos installer contract](../../decisions/talos-image-factory.md)
- [Validation](../../architecture/validation.md)
