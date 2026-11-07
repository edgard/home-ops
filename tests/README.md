# Validation

Native tools check syntax, schemas, deprecations, and language conventions.
pytest is the single runner for repository assertions, adapter units, and
isolated Ansible execution. Configuration is read directly from YAML, TOML,
JSON5, and tracked HCL sources. There is no normalized policy inventory.

| Command | Responsibility |
| --- | --- |
| `task deps` | Synchronize locked Python tools and pinned Ansible collections |
| `task fmt` | Format YAML, Python/imports, and Terraform |
| `task fmt:check` | Check the same formatting without modifying files |
| `task lint` | All native static checks and backendless OpenTofu validation |
| `task test` | All configuration, unit, and integration cases |
| `task test -- tests/config/wiki` | Focus pytest on wiki checks; any pytest path/options work |
| `task check` | Formatting checks, static checks, then the complete test suite once |

Focused native commands are `lint:yaml`, `lint:python`, `lint:config`,
`lint:workflows`, `lint:ansible`, and `lint:terraform`. `lint:ansible` runs only
production-profile ansible-lint. Configuration assertions, unit tests, isolated
integration scenarios, and the Kubernetes Helm/kubeconform/Pluto pipeline belong
to pytest. The old pytest-backed `lint:wiki`, `lint:repository`, and
`lint:kubernetes` commands, `lint:static`, `lint:ansible:static`, and `precommit`
were removed without aliases.

Run `task deps` first. uv synchronizes the default development group from the
committed lock into `.venv`; pinned collections remain in
`ansible/requirements.yml`. Python 3.14 must already be installed; `PYTHON_BIN`
selects the interpreter within the supported project range. Machine tools belong
to Homebrew/Chezmoi, not this repository's dependency installer. Local tools include
uv, Task, OpenTofu, yamlfmt, actionlint, ShellCheck, Node 24 or newer, Helm,
kubeconform, Pluto, and SecretSpec matching the CLI role defaults. The installer
scenario also needs Bash, tar with xz support, and sha256sum. Python lint, format,
and schema CLIs come from `.venv`, not global installations. Missing tools fail
rather than silently skipping required checks.

Checks never synchronize the environment or change a lockfile. `lint:python`
verifies Python lock freshness; update dependencies deliberately with `uv lock`,
then run `task deps`. Direct pins remain Renovate-managed, while the supported
Python range is manually reviewed with Ansible upgrades. OpenTofu validates with
a temporary data directory and a read-only root provider lock, without using the
remote backend. The tracked provider lock supports macOS ARM64 and Linux AMD64;
`tf:clean` preserves it. Updating provider pins requires a matching lock update.

CI runs Format, Lint, and one full Tests job. Tests use ordinary pytest discovery,
so new directories participate automatically. Quality Gate requires all three
jobs to succeed, and CI retains JUnit results even when tests fail. Toolchain
setup uses locked Python dependencies, role-owned SecretSpec compatibility,
and checksum/version validation of the staged installer. Isolated installer
scenarios cover success, rejected checksums/versions, binary preservation, and
staging cleanup. These offline checks may download charts/providers/packages;
they require no live cluster or cloud credentials.

All pytest commands, including focused checks and direct invocations, use the
parallel defaults in [pyproject.toml](../pyproject.toml): automatic worker
selection capped at four, with the standard work-stealing scheduler. Every test
participates without eligibility markers or file lists. Use
`.venv/bin/python -m pytest -n 0` or `PYTEST_ADDOPTS="-n 0" task test` for serial
debugging. The same environment override works with `task check`.

`config/wiki` checks documentation sources and links. `config/repository` and
`config/kubernetes` assert relationships and explicit
safety limits. `unit` tests focused runtime adapters. `integration` runs real role
entry points and Task commands with synthetic inputs. Test helpers live in
`support`; disposable playbooks only invoke roles and export observed facts.
`conftest.py` is pytest's ordinary fixture filename, unrelated to the retired
Conftest CLI.

The Kubernetes fixture checks sources before invoking Helm, kubeconform, and
Pluto directly through an ordinary test helper. It owns an empty, private,
nonsymlink output directory and removes it after success or failure. A bounded
interprocess file lock coordinates consumers across modules and workers: one
initializer renders and validates, cleans up its workspace, then atomically
publishes parsed documents in a private snapshot for this pytest run. Each
worker loads its own objects. Failures retain native diagnostics and prevent
other workers from retrying or consuming partial output. An abruptly terminated
initializer leaves an interruption marker; pytest's temporary-directory
retention handles files left by a process that cannot run cleanup.

The helper renders `rendered/<category>/<app>.yaml`, exports served CRD schemas,
and runs schema/deprecation checks. Chart caching and Helm paths are isolated
per run; local served schemas take precedence over default/catalog schemas.
The [xdist fixture recipe](https://pytest-xdist.readthedocs.io/en/stable/how-to.html#making-session-scoped-fixtures-execute-only-once)
explains why session scope alone does not coordinate multiple workers.

Ansible tests use temporary HOME/config paths, sanitized environments, bounded
subprocesses, explicit fake CLIs, and a loopback Kubernetes API. The actual
Kubernetes collection handles reads, patches, scaling, waits, and deletion.
Only pod exec substitutes a module: destructive command strings are recorded,
never executed on the host. A separate real-module connection test guards its
import boundary. Native dry-run requests retain fixture state. Production roles
have no test-only execution mode. The platform identity URL has a nonsecret role
default so authenticated preflight can use a controlled HTTP endpoint.

Security exceptions remain narrowly scoped to the existing image prefixes:
root-dependent application entrypoints, LinuxServer startup, VPN networking,
Restic, and bundled chart services. LinuxServer and Karakeep root allowances do
not exempt their capability/escalation checks. Shared media requires group zero;
Paperless GPT requires its three startup capabilities. Tests exercise valid and
invalid cases alongside the current checkout.

Prefer a native validator for a standard requirement. Add a plain assertion for
an operational relationship, and a real entry-point scenario for role behavior.
Derive versions, addresses, ports, item references, and original resource state
from their owner. Avoid task display names, positions, counts, equivalent source
spellings, copied pins, test discovery wrappers, and a new assertion framework.
New fixtures must isolate mutable files and external resources with pytest
temporary paths and dynamically allocated ports. Coordinate shared work in its
own fixture rather than adding scheduling exceptions. Keep parametrized
collection deterministic and preserve subprocess cleanup and credential isolation.

These checks cover offline safety and configuration. They do not prove live pod
websocket transport, a real restore, fresh-cluster installation, or deployed
application behavior. Deployment acceptance still requires targeted live checks.
