# Native validators and one pytest suite

Purpose: record validation ownership and the simplification decision.
Status: current. Reviewed against: `9f966763020631cd9bab2de5ddd8471434b71876`.

The earlier validation refactors retired top-level scripts and separated
configuration assertions from executable behavior. Their inventories, Rego rules,
static task reconstruction, and nested test runners still created unnecessary
plumbing. The unified suite now reads original source objects and invokes real
role entry points through pytest.

Ansible retains operator orchestration and runtime safety checks. pytest owns
offline wiki checks and invokes the native chart/schema/deprecation tools directly.
Native formatters, linters, Git, OpenTofu, kubeconform, and Pluto
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

The Kubernetes fixture validates sources first, invokes the native pipeline in
a private workspace, shares the resulting render once, and owns cleanup. Offline
validation roles and playbooks have been removed. Served CRD
schemas remain authoritative; strict validation and catalog fallback retain their
previous behavior. Local and CI commands use the same complete pytest discovery. CI runs one full
Tests job alongside Format and Lint; `task check` composes those commands locally.
Static checks never run pytest or synchronize dependencies. Python tools are
locked through uv, while machine tools remain outside the repository installer.
Single formatters own YAML, Python, and Terraform; shared native schema tooling
validates standard configuration rather than bespoke assertions.

Global pytest defaults parallelize every case with a bounded worker count and
the standard work-stealing scheduler. Fixtures own mutable-resource isolation;
there are no test eligibility lists or scheduling markers. The rendering fixture
uses a file lock and atomically published per-run snapshot so session fixtures
do not repeat chart downloads in different workers. Consumers load independent
objects, and failed or interrupted initialization cannot publish usable results.
The standard `-n 0` option provides serial debugging.

## Sources

- [Test guide](../../../tests/README.md)
- [CI workflow](../../../.github/workflows/ci.yml)
- [Taskfile](../../../Taskfile.yaml)
- [Native Kubernetes pipeline](../../../tests/support/kubernetes.py)
- [Rendering fixture](../../../tests/config/kubernetes/conftest.py)
- [pytest configuration](../../../pyproject.toml)
- [Earlier validation refactor, PR #409](https://github.com/edgard/home-ops/pull/409)

## Related pages

- [Validation](../architecture/validation.md)
- [Agent workflow](../agent-workflow.md)
