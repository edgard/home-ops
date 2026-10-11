# Validation and PR gate

Purpose: distinguish local checks, repository policy, and deployment evidence.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

`task lint` aggregates formatting, static analysis, wiki, workflow, Ansible,
Kubernetes, and Terraform validation. Source, metadata, raw manifest, and
rendered workload policy check repository contracts; Ansible tests exercise
role behavior and fixtures. The Ansible gate also runs synthetic Python secret,
bootstrap, token rollback, and pinned SecretSpec integration tests. CI has no
cloud credentials; these tests do not prove a fresh-cluster bootstrap. CI runs focused targets as separate pull-request
jobs and collects their results in `Quality Gate`.

Kubernetes schema validation renders the pinned charts with their CRDs first.
Served schemas from both tracked CRDs and those charts take precedence over the
external catalog. The exporter validates schema structure and adds strict unknown
field checks while respecting composition branches, explicit map schemas, nullable
fields, integer/string fields, and preserved unknown fields. A shared safe YAML
parser handles chart scalar defaults for both schema export and route coverage.
Missing served schemas, malformed definitions, conflicting versions, invalid
resource fields, and unknown resource kinds remain errors. This uses the deployed
API definitions and avoids depending on a separately converted catalog entry
when the authoritative schema is available.

The [validation architecture decision](../decisions/validation-architecture.md)
explains the replacement of the former scripts directory. These checks prove
the committed configuration satisfies the tested contracts, not that a synced
application functions in the live cluster. Deployment acceptance requires
targeted runtime checks.

## Sources

- [Taskfile](../../../Taskfile.yaml)
- [CI workflow](../../../.github/workflows/ci.yml)
- [CRD schema exporter](../../../ansible/roles/kubernetes_validation/files/export_schemas.py)
- [Kubernetes validation playbook](../../../ansible/playbooks/validate-kubernetes.yml)
- [Wiki validation playbook](../../../ansible/playbooks/validate-wiki.yml)
- [Policy tree](../../../policy)

## Related pages

- [GitOps delivery](gitops-delivery.md)
- [Agent workflow](../agent-workflow.md)
