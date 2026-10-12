# Validation and PR gate

Purpose: distinguish local checks, repository policy, and deployment evidence.
Status: current. Reviewed against: `6aeb7489ec815222523c414983c8678bb5fd93bc`.

`task lint` aggregates formatting, static analysis, wiki, workflow, repository,
Ansible, Kubernetes, and Terraform validation. Policies own assertions about
committed configuration; behavior tests exercise the adapters, roles, and native
commands that consume it. The [policy guide](../../../policy/README.md) defines
these boundaries and the input layer for each policy tree.

`task lint:repository` checks Task interfaces, SecretSpec ownership and scopes,
infrastructure inputs, Talos compatibility, and validation wiring through the
repository validation role. Git supplies native tracked/ignored credential
artifact checks. `task lint:ansible` runs Ansible lint, the static role policy
runner, and disposable setup, cleanup, preflight, bootstrap, restore, and token
rollback fixtures. Static role policy identifies operations by their modules and
resource identities; harmless task additions and renaming must remain valid.

`task lint:kubernetes` runs metadata and source policies, including cross-file
application configuration, then raw/rendered resource policy, schema, deprecation,
and aggregate route-coverage checks. Parsing and inventory construction stay in
validation roles; compatibility, safety, and content decisions stay in policy.
Native wiki, Git, schema, and deprecation tools retain their own lint semantics.

Python tests under `ansible/tests/unit` include provider/parser units and isolated
integration fixtures for inventory construction, policy invocation, Talos
commands, OpenTofu sensitivity, and pinned SecretSpec. Policy regression cases
live beside their rules in `*_test.rego`. Runtime assertions in operator roles
still validate live inputs and state; offline policy cannot replace them. CI has
no cloud credentials, so these fixtures do not prove a fresh-cluster bootstrap.
The Ansible CI job runs repository, role, behavior, and wiki validation; the other
focused jobs join it in `Quality Gate`.

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
- [Role policy runner](../../../ansible/playbooks/validate-ansible.yml)
- [Repository policy runner](../../../ansible/playbooks/validate-repository.yml)
- [Policy boundary guide](../../../policy/README.md)
- [Operator behavior fixtures](../../../ansible/tests/unit/test_operator_patterns.py)

## Related pages

- [GitOps delivery](gitops-delivery.md)
- [Agent workflow](../agent-workflow.md)
