# Validation and PR gate

Purpose: distinguish native validation, repository assertions, and deployment evidence.
Status: current. Reviewed against: `9f966763020631cd9bab2de5ddd8471434b71876`.

`task check` runs formatting checks, native static checks, and the complete
pytest suite once. `task fmt` changes formatting, `task fmt:check` verifies the
same formatting, `task lint` performs static analysis, and `task test` owns all
pytest discovery. Focus tests with `task test -- <path or pytest options>`.
The [test guide](../../../tests/README.md) describes ownership and prerequisites.
CI runs the same commands in Format, Lint, and one full Tests job; the required
`Quality Gate` rejects failed, cancelled, or skipped dependencies. Tests publish
JUnit results, including on failure. New pytest directories need no CI edits.

YAML formatting uses yamlfmt alone, including quote style. Ruff formats Python
and imports and checks a focused correctness/import rule set. Native yamllint,
production-profile ansible-lint, actionlint with required ShellCheck, and bundled
Taskfile/Renovate/composite-action schemas retain their specialized checks.
Python tools and dependencies live in the non-packaged project metadata and
committed uv lock; `task deps` performs locked synchronization and installs pinned
collections. Python is supplied by machine setup, with the supported range
reviewed alongside Ansible. Lint checks lock freshness without synchronizing.
Checks and tests never rewrite locks or install dependencies. Scoped secret
commands put the project interpreter first on PATH so the standalone provider
uses the supported Python even when the machine default differs.

OpenTofu initialization is backendless, noninteractive, uses temporary provider
data, and verifies the committed root lock read-only before validation. Provider
pins, OpenTofu registry identities, and checksums for macOS ARM64/Linux AMD64 stay
reviewable. `tf:clean` preserves the lock. Renovate manages dependency/lock updates;
configuration validation alone does not prove discovery or artifact generation.

All pytest invocations inherit automatic parallelism capped at four workers
and work-stealing scheduling from [pytest configuration](../../../pyproject.toml).
Every test participates; resource isolation belongs to fixtures rather than
test eligibility lists. Use `PYTEST_ADDOPTS="-n 0" task test` for serial debugging.

pytest reads source YAML/TOML/JSON5 and Git-tracked HCL directly. Configuration
checks protect metadata and source conventions, application wiring, SecretSpec
ownership/scopes, compatibility bounds, credential artifacts, raw/rendered
resource guardrails, and route coverage. Native tools retain syntax, lint,
schema, and deprecation semantics. Conftest/Rego, normalized policy inventories,
static task-operation catalogs, and nested Ansible test runners are retired.

Wiki checks use plain pytest for links, page structure, index reachability, and
app-page coverage. Ansible contains only operator orchestration and runtime guards.

Unit tests exercise safe provider/material parsers and schema export. Integration
tests invoke real Ansible entry points and Task commands with synthetic inputs,
temporary paths, sanitized environments, fake CLIs, and a loopback API. The real
Kubernetes collection handles REST operations; pod exec records commands through
one test-only module. Another case loads the real exec module and reaches its
connection boundary. This does not prove live websocket transport or restoration.

Operational assertions cover check mode, confidentiality, exact Talos server
versions, private-material cleanup, CI tool checksum/version rejection, scoped delivery, token rollback,
committed handoff, original restore state, and failure evidence. Restore failure
may leave workloads paused or partially resumed; tests retain that recovery
contract. Roles contain no test-only execution branches. Runtime assertions
continue to protect operator inputs and live state. Injected API-error scenarios
use a separate bounded budget from deliberate timeout scenarios; a delayed
synthetic response verifies that the intended target-read fault is reached.

The CI SecretSpec installer scenario executes the toolchain action's real shell
against synthetic release archives. It verifies successful installation, rejected
checksums or binary versions, preservation of an existing executable on rejection,
and staging cleanup. The version comes from the CLI role defaults in both CI and
runtime validation.

The rendering fixture validates sources first and owns an empty private output
directory. An ordinary test helper renders pinned charts with CRDs, exports served
schemas, and invokes kubeconform/Pluto directly. It retains per-run caching and isolated Helm
paths, writes `rendered/<category>/<app>.yaml`, and leaves cleanup to its caller.
Rendered tests across modules and workers share one pipeline invocation through
a bounded file lock. After validation and workspace cleanup, the fixture publishes
a private snapshot atomically; workers parse independent copies. Initialization
failures preserve diagnostics and block partial-result reuse or retries. Forced
termination leaves an interruption marker and pytest-managed temporary files.
Source/unit tests need no rendering.

Repository/chart served schemas precede the default/catalog fallback. Export
preserves schema keyword/property distinctions, composition, maps, nullable and
integer/string fields, and explicitly preserved unknown fields. Missing, malformed,
conflicting schemas, unknown kinds, and invalid fields fail closed. The shared
safe loader supports chart scalar defaults and safe embedded Recyclarr YAML.

The [architecture decision](../decisions/validation-architecture.md) records the
simplification. Offline checks supplement targeted deployment acceptance; they
are not evidence that a synced application functions in the running cluster.

## Sources

- [Taskfile](../../../Taskfile.yaml)
- [CI workflow](../../../.github/workflows/ci.yml)
- [Test guide](../../../tests/README.md)
- [Configuration assertions](../../../tests/config)
- [Integration scenarios](../../../tests/integration)
- [CRD schema exporter](../../../tests/support/schemas.py)
- [Native Kubernetes pipeline](../../../tests/support/kubernetes.py)
- [Rendering fixture](../../../tests/config/kubernetes/conftest.py)
- [Parallel resource regression scenarios](../../../tests/integration/test_parallel.py)
- [CI tool installation scenarios](../../../tests/integration/test_ci_tools.py)
- [Python dependencies, lint, and pytest configuration](../../../pyproject.toml)
- [Python lock](../../../uv.lock)
- [Provider lock](../../../terraform/.terraform.lock.hcl)
- [Wiki checks](../../../tests/config/wiki/test_wiki.py)

## Related pages

- [GitOps delivery](gitops-delivery.md)
- [Agent workflow](../agent-workflow.md)
