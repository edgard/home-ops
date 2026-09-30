# Keep validation close to its contracts

Purpose: record the current validation layout and its reason.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

[PR #258](https://github.com/edgard/home-ops/pull/258) split CI into focused
jobs with a required aggregate gate. [PR #409](https://github.com/edgard/home-ops/pull/409)
retired the former scripts directory while retaining deployment, credential,
restore, route, and manifest checks in Ansible roles/tests and Conftest policy.
Local `task lint` runs the same focused checks. Keep new assertions with the
source layer they protect, and check operational invariants instead of pinning
test expectations to names or dependency versions without a behavioral reason.

## Sources

- [CI workflow](../../../.github/workflows/ci.yml)
- [Taskfile](../../../Taskfile.yaml)
- [Validation role](../../../ansible/roles/kubernetes_validation/tasks)
- [Policy tree](../../../policy)
- [Validation refactor, PR #409](https://github.com/edgard/home-ops/pull/409)

## Related pages

- [Validation](../architecture/validation.md)
- [Agent workflow](../agent-workflow.md)
