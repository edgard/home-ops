# Native validators and one pytest suite

Purpose: record validation ownership and the simplification decision.
Status: current. Reviewed against: `e66f8dac017406e0b72605aa16d5f7862aaa0c8a`.

The earlier validation refactors retired top-level scripts and separated
configuration assertions from executable behavior. Their inventories, Rego rules,
static task reconstruction, and nested test runners still created unnecessary
plumbing. The unified suite now reads original source objects and invokes real
role entry points through pytest.

Ansible retains operator orchestration and native chart/schema/deprecation work.
Native formatters, linters, Git, wiki validation, OpenTofu, kubeconform, and Pluto
keep their specialized semantics. Plain pytest assertions cover repository
relationships; units cover focused adapters; isolated scenarios cover execution,
check mode, rollback, cleanup, confidentiality, and original-state restoration.
There is no policy engine or generic contract registry.

Tests derive operational versions and identities from owning configuration.
Fixed compatibility bounds and reasoned security exceptions remain explicit.
Task names, task positions, and equivalent source expressions are not behavior.
The real Kubernetes collection talks to a loopback API; the unsupported pod-exec
transport is one controlled module boundary, with separate real-module loading.
Offline fixtures do not replace fresh-cluster or live application acceptance.

The Kubernetes role accepts a caller-owned private workspace. pytest validates
sources first, shares the resulting render once, and owns cleanup. Served CRD
schemas remain authoritative; strict validation and catalog fallback retain their
previous behavior. Local and CI commands cover the same disjoint pytest subsets.

## Sources

- [Test guide](../../../tests/README.md)
- [CI workflow](../../../.github/workflows/ci.yml)
- [Taskfile](../../../Taskfile.yaml)
- [Kubernetes validation role](../../../ansible/roles/kubernetes_validation/tasks/main.yml)
- [Earlier validation refactor, PR #409](https://github.com/edgard/home-ops/pull/409)

## Related pages

- [Validation](../architecture/validation.md)
- [Agent workflow](../agent-workflow.md)
