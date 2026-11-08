# Validation

Keep permanent validation small: native tools validate deployment configuration;
a few serial, offline pytest checks protect credentials, data, infrastructure
compatibility, and wiki links. Executable adapters and `test_*.py` files live
here together; pytest does not run Helm or contact a cluster.

| Command | Responsibility |
| --- | --- |
| `task deps` | Synchronize locked Python tools and pinned operator collections |
| `task fmt` / `task fmt:check` | Format / check YAML, Python, and Terraform |
| `task lint` | Native syntax, schema, workflow, Ansible, OpenTofu, and Kubernetes validation |
| `task lint:kubernetes` | Render every app, then run kubeconform, Pluto, and data guards |
| `task test` | Run the small serial offline suite |
| `task test -- validation/test_wiki.py` | Check wiki links and app-page coverage |
| `task check` | Formatting checks, native validation, and offline tests |

Run `task deps` first. Python must satisfy the project metadata; uv never downloads
an interpreter. Native local tools are Task, uv, yamlfmt, OpenTofu, actionlint,
ShellCheck, Helm, kubeconform, and Pluto. SecretSpec/BWS remain operator prerequisites,
not test prerequisites. Checks never install dependencies or rewrite locks.
OpenTofu validation uses temporary provider data, no backend, and the committed
root provider lock read-only.

CI keeps Format, Lint, Tests, and Quality Gate. All profiles synchronize the same
Python lock; only Lint installs Ansible collections and Kubernetes validators.
Format also needs OpenTofu for formatting. Tests needs no operator CLI, native
Kubernetes CLI, collection installation, credentials, or live services. JUnit
results are retained even on failure; Quality Gate requires every job to succeed.

## Permanent checks

- Secret scopes/project alignment and ignored/untracked sensitive artifacts.
- Production secret-provider rejection/redaction, secret-delivery predicates,
  and Talos identity validation.
- Talos installer/target alignment and migration bounds, interpreter alignment,
  and the Cloudflare provider constraint relationship.
- CRD schema conversion, wiki local links, and app-page coverage.
- Raw/rendered populated Secrets; app-template PVC rollout replicas/strategy;
  shared-media group/ownership policy; Paperless GPT persistence, complete OCR,
  original PDFs, existing metadata, and shared data ownership.

The serial Kubernetes adapter owns a temporary workspace, private Helm homes,
and a small explicit environment. It pulls each distinct chart once per run,
renders all apps including CRDs, exports served schemas, then runs native
validators. It has bounded subprocesses/retries and cleans up on success or
failure. CRD conversion and schema precedence retain their existing behavior;
kubeconform has no new `-strict` or missing-schema exemption. Raw validation
skips CRDs and RenovateJob; rendered validation skips only CRDs.

Failures identify the app/tool/resource without echoing manifests, rejected
values, or parser excerpts. HTTP status codes can be reported for downloads.
For a detailed native diagnostic, reproduce locally with synthetic/nonsecret
inputs; do not publish raw configuration payloads in CI logs.

## Development cycle

Use extensive change-specific testing during implementation when useful. Before
merge, remove temporary tests and fixtures and summarize commands/results in the
PR. Keep a permanent test only for one of the concrete risks above, with minimal
deterministic code that native validation does not already cover. No blanket
requirement for a lasting test per behavior change, coverage quota, simulation
framework, disabled legacy suite, or tests of the runner/toolchain.

Ordinary startup, probes, model/temperature settings, and app API compatibility
do not become permanent tests by being called compatibility checks. Existing
Renovate limits and runtime safeguards remain in their owning configuration.
Lifecycle, restore/rollback, transport, and installer simulations are removed.
Changes to those operations need targeted implementation verification and review;
the permanent suite does not prove a live restore, bootstrap, or application.
