# Validation

Native tools check syntax, schemas, deprecations, and language conventions.
pytest is the single runner for repository assertions, adapter units, and
isolated Ansible execution. Configuration is read directly from YAML, TOML,
JSON5, and tracked HCL sources. There is no normalized policy inventory.

| Command | Responsibility |
| --- | --- |
| `task test` | All configuration, unit, and integration cases |
| `task lint:wiki` | Wiki links, page structure, index reachability, and app-page coverage |
| `task lint:repository` | SecretSpec scopes/ownership, compatibility, Task interfaces, native Git artifact checks |
| `task lint:ansible` | Production-profile ansible-lint, then unit and integration cases |
| `task lint:ansible:static` | Production-profile ansible-lint only |
| `task lint:kubernetes` | Source/raw/rendered assertions plus native Helm, kubeconform, and Pluto pipeline |
| `task lint` | Format/static/workflow/Ansible/OpenTofu checks, then all pytest cases once |

Run `task deps` first. Local prerequisites include Python 3.14, Node 24 or newer,
OpenTofu, pinned SecretSpec (`task secrets:setup`), and the existing native lint
and Kubernetes CLIs. CI installs these in the corresponding toolchain profiles.
Ansible's focused subset requires no real Helm/kubeconform/Pluto installation.
Missing dependencies fail the checks; required cases never silently skip.

All pytest commands, including focused checks and direct invocations, use the
parallel defaults in [pyproject.toml](../pyproject.toml): automatic worker
selection capped at four, with the standard work-stealing scheduler. Every test
participates without eligibility markers or file lists. Use
`.venv/bin/python -m pytest -n 0` or `PYTEST_ADDOPTS="-n 0" task test` for serial
debugging. The same environment override works with `task lint`.

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
