# Native validators and minimal permanent checks

Purpose: record the boundary between implementation verification and permanent validation.
Status: current. Reviewed against: `f73a66d4d60b9fd7e373eb1cfcbde4e8df270083`.

Native tools validate deployable configuration. A small serial offline pytest
suite protects concrete credential, data, platform compatibility, schema-conversion,
and wiki-link risks. Executable validators and their small tests share one
validation directory. Kubernetes rendering runs separately from pytest, through
a thin serial adapter; there is no generic policy registry or test orchestration.

The previous lifecycle/API/CLI simulations and parallel rendering infrastructure
are removed. Their ongoing bootstrap, restore, rollback, installer, and transport
coverage is deliberately retired. Operational Ansible guards remain unchanged.
One-off verification belongs to the change that needs it: temporary tests can be
extensive during implementation, then are removed before merge with results
recorded in the PR. Permanent tests must justify one of the retained risks, not
merely repeat configuration, source spelling, or a past startup/API incident.

All-app Helm rendering, served-CRD schema export, kubeconform, and Pluto remain
required, with existing schema semantics and explicit exceptions. They use
ordinary temporary directories and subprocesses; no file locks, workers, shared
snapshots, fake services, or custom process-runner framework remain. External
chart/schema availability can still block a PR.

Local and CI commands retain the same gate. CI Tests synchronizes locked Python
without operator tools or collections, while Lint owns native deployment checks.
No coverage target or permanent code-size enforcement is introduced. Runtime
and live acceptance evidence remain separate from offline validation.

## Sources

- [Contributor policy](../../../AGENTS.md)
- [Validation guide](../../../validation/README.md)
- [Taskfile](../../../Taskfile.yaml)
- [CI workflow](../../../.github/workflows/ci.yml)
- [Native Kubernetes adapter](../../../validation/kubernetes.py)
- [Schema conversion](../../../validation/schemas.py)
- [Python dependency and pytest configuration](../../../pyproject.toml)

## Related pages

- [Validation architecture](../architecture/validation.md)
- [Agent workflow](../agent-workflow.md)
