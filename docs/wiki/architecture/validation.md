# Validation and PR gate

Purpose: distinguish native deployment validation, small offline checks, and live evidence.
Status: current. Reviewed against: `f73a66d4d60b9fd7e373eb1cfcbde4e8df270083`.

`task check` runs formatting checks, native lint/deployment validation, and the
small serial pytest suite once. `task lint:kubernetes` renders every app and
runs kubeconform/Pluto plus data guards; `task test` remains offline and supports
normal pytest arguments. See the [validation guide](../../../validation/README.md).

Native formatters, yamllint, Ruff, actionlint/ShellCheck, ansible-lint, bundled
configuration schemas, and backendless OpenTofu validation retain their roles.
Python dependencies are locked; checks neither install dependencies nor rewrite
locks. OpenTofu uses temporary provider data and the root lock read-only.

Kubernetes validation is a serial native-tool adapter with a private temporary
workspace and isolated Helm homes/environment. It discovers app metadata/values,
owned raw `.yaml`/`.yml` manifests, and Argo CD sources, not arbitrary repository YAML. Each
chart is pulled once per run. Served CRD schemas precede default/catalog fallback.
Existing CRD strictness, composition, nullable/int-or-string handling, preserved
unknown fields, conflict rejection, and safe YAML loading are retained. No new
kubeconform `-strict` flag is implied. Raw skips CRDs and RenovateJob; rendered
validation skips only CRDs. Tool failures and unknown schemas fail the gate.
Download failures still block PRs. Diagnostics omit configuration payloads.

Data guards reject populated Secrets and unsafe app-template PVC rollout settings,
preserve shared-media ownership, and protect Paperless GPT persistence and
non-destructive OCR/metadata settings. One replica and Deployment Recreate do
not establish exclusive access across apps or external NFS writers.

The offline suite covers credential scopes/artifacts, production secret/material
functions, platform compatibility relationships, schema conversion, and wiki
links/app-page coverage. It has no fake CLI/API services, worker coordination,
snapshots, mutation matrices, or tests of the test harness. Broad workload-security,
route-coverage, startup/probe, and app feature/API assertions are no longer part
of the permanent gate; configured safeguards remain in manifests and review.

CI preserves Format, Lint, Tests, and Quality Gate. Lint installs Kubernetes tools
and Ansible collections. Tests performs locked Python synchronization without
collections or native/operator CLIs. Format still needs OpenTofu for formatting.
JUnit results are uploaded on failure; failed, cancelled, or skipped dependencies
reject Quality Gate.

Extensive implementation verification is allowed, but temporary tests/fixtures
are removed before merge and evidence is summarized in the PR. Retain only small
checks for the enumerated risks; do not turn every implementation detail or prior
outage into a permanent contract. Runtime operator guards remain authoritative.
Removing lifecycle simulations intentionally removes ongoing bootstrap, restore,
rollback, and transport regression coverage. Native validation does not prove
those live operations or deployed application behavior.

## Sources

- [Root contributor rules](../../../AGENTS.md)
- [Taskfile](../../../Taskfile.yaml)
- [CI workflow](../../../.github/workflows/ci.yml)
- [CI toolchain](../../../.github/actions/setup-toolchain/action.yml)
- [Validation guide](../../../validation/README.md)
- [Native Kubernetes adapter](../../../validation/kubernetes.py)
- [Data guards](../../../validation/data.py)
- [CRD schema exporter](../../../validation/schemas.py)
- [Repository checks](../../../validation/test_repository.py)
- [Wiki checks](../../../validation/test_wiki.py)
- [Python metadata](../../../pyproject.toml) and [lock](../../../uv.lock)
- [Provider lock](../../../terraform/.terraform.lock.hcl)

## Related pages

- [Validation decision](../decisions/validation-architecture.md)
- [Agent workflow](../agent-workflow.md)
- [GitOps delivery](gitops-delivery.md)
