# Validation and PR gate

Purpose: distinguish local checks, repository policy, and deployment evidence.
Status: current. Reviewed against: `d897e58d4dbc5cd0609e9b6dc3098d88fb887639`.

`task lint` aggregates formatting, static analysis, wiki, workflow, Ansible,
Kubernetes, and Terraform validation. Source, metadata, raw manifest, and
rendered workload policy check repository contracts; Ansible tests exercise
role behavior and fixtures. The Ansible gate runs native role contracts and disposable setup, preflight,
bootstrap, and token rollback fixtures. Focused Python tests under `ansible/tests/unit`
cover the provider adapter, pure readiness/schema predicates, isolated Talos
generation, and pinned SecretSpec integration. CI has no
cloud credentials; these tests do not prove a fresh-cluster bootstrap. CI runs focused targets as separate pull-request
jobs and collects their results in `Quality Gate`.

Kubernetes schema validation renders the pinned charts with their CRDs first.
Served schemas from both tracked CRDs and those charts take precedence over the
external catalog. The exporter validates schema structure and adds strict unknown
field checks while respecting composition branches, explicit map schemas, nullable
fields, integer/string fields, and preserved unknown fields. A shared safe YAML
parser handles chart scalar defaults for both schema export and route coverage.
Sensitive YAML/JSON parsing emits safe categories instead of source excerpts.
Native API failures use explicit result-shape checks to suppress raw provider
diagnostics; a captured fixture-playbook run enforces output redaction alongside
transaction and rollback behavior.

Role contracts identify operations by their modules and resource identities.
Harmless task additions and renaming must not fail the gate; credential checks,
mutation ordering, cleanup branches, and original-state restoration remain
enforced. Operator fixtures also check that confirmed restores skip execution
in check mode and that Talos verification compares the server tag exactly.
SecretSpec installation, validation, and integration tests share the role's
configured pin. Discovery checks cover the operator-tool Renovate manager.

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
- [Role contracts](../../../ansible/tests/role-contracts.yml)
- [Operator behavior fixtures](../../../ansible/tests/unit/test_operator_patterns.py)

## Related pages

- [GitOps delivery](gitops-delivery.md)
- [Agent workflow](../agent-workflow.md)
