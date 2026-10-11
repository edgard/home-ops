# Keep validation close to its contracts

Purpose: record the current validation layout and its reason.
Status: current. Reviewed against: `2fe88a7bb0b8bde1fc9857626c53bf17d5379295`.

[PR #258](https://github.com/edgard/home-ops/pull/258) split CI into focused
jobs with a required aggregate gate. [PR #409](https://github.com/edgard/home-ops/pull/409)
retired the former scripts directory while retaining deployment, credential,
restore, route, and manifest checks in Ansible roles/tests and Conftest policy.
Secret workflows also follow this layout: Task launches native SecretSpec,
Ansible roles own orchestration, and focused adapters and unit fixtures remain
under Ansible. The completed state-migration helper is retained only in Git history.
Local `task lint` runs the same focused checks. Keep new assertions with the
source layer they protect, and check operational invariants instead of pinning
test expectations to names or dependency versions without a behavioral reason.

The Kubernetes role renders pinned charts before raw schema validation, exporting
served CRD schemas alongside repository-owned CRDs. The exporter traverses schema
keywords separately from property-name maps, so a field named `properties` cannot
corrupt its containing schema. Strict validation stays enabled; no resource is
exempted because a remote catalog conversion is malformed. The external catalog
remains a fallback for APIs without a repository or chart schema.

## Sources

- [CI workflow](../../../.github/workflows/ci.yml)
- [Taskfile](../../../Taskfile.yaml)
- [Validation role](../../../ansible/roles/kubernetes_validation/tasks)
- [Policy tree](../../../policy)
- [Validation refactor, PR #409](https://github.com/edgard/home-ops/pull/409)

## Related pages

- [Validation](../architecture/validation.md)
- [Agent workflow](../agent-workflow.md)
