# Home Ops

This is a single-node Talos and Argo CD GitOps repository. Make changes on a
branch through a pull request. Never commit directly to `master`.

Start repository questions at the [wiki index](docs/wiki/index.md) and verify
claims against current sources. Before changing the repo, read the
[agent workflow](docs/wiki/agent-workflow.md). Follow the
[wiki conventions](docs/wiki/AGENTS.md) and update affected pages in the same
PR as substantive changes. Routine version bumps need a wiki edit only when
the explanation changes. On the first substantive PR each month, check the
[log](docs/wiki/log.md) and follow the [monthly review rule](docs/wiki/AGENTS.md#review).

## Validation

Run `task fmt` and `task check` before committing. Use change-specific
verification, remove temporary tests and fixtures before merge, and record
commands and results in the PR. Keep runtime safeguards in operational code.
Retain a permanent test only for a concrete credential, data, selected platform
compatibility, schema-conversion, or wiki-integrity risk beyond native checks.
Keep it small, deterministic, serial, and offline. Follow the
[validation guide](validation/README.md#development-cycle) for exclusions and examples.
