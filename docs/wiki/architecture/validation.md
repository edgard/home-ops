# Validation and PR gate

Purpose: distinguish native validation, repository assertions, and deployment evidence.
Status: current. Reviewed against: `df530ab8f6edc603500f39fb634d6c404b64c636`.

`task lint` runs formatting, YAML/workflow checks, production-profile Ansible
lint, backendless OpenTofu validation, then the complete pytest suite once.
The [test guide](../../../tests/README.md) describes ownership and prerequisites.
CI runs disjoint focused subsets in its Ansible and Kubernetes jobs, alongside
the other native jobs, and requires their combined `Quality Gate`.

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
versions, private-material cleanup, tool checksums, scoped delivery, token rollback,
committed handoff, original restore state, and failure evidence. Restore failure
may leave workloads paused or partially resumed; tests retain that recovery
contract. Roles contain no test-only execution branches. Runtime assertions
continue to protect operator inputs and live state.

The rendering fixture validates sources first and owns an empty private output
directory. An ordinary test helper renders pinned charts with CRDs, exports served
schemas, and invokes kubeconform/Pluto directly. It retains per-run caching and isolated Helm
paths, writes `rendered/<category>/<app>.yaml`, and leaves cleanup to its caller.
Rendered tests share one pipeline invocation; source/unit tests need no rendering.

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
- [Wiki checks](../../../tests/config/wiki/test_wiki.py)

## Related pages

- [GitOps delivery](gitops-delivery.md)
- [Agent workflow](../agent-workflow.md)
