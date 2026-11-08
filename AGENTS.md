# Home Ops

This is a single-node Talos and Argo CD GitOps repository. Make changes on a
branch through a pull request; never commit directly to `master`.

Before changing the repository, read [the detailed workflow](docs/wiki/agent-workflow.md).
For any repository question, start at the [wiki index](docs/wiki/index.md),
follow the relevant pages, and verify their claims against current sources.
For substantive configuration, policy, or procedure changes, check related
wiki pages and update affected explanations in the same PR. Routine version
bumps need no wiki edit when the explanation remains accurate. Follow the
[wiki conventions](docs/wiki/AGENTS.md) for queries, ingests, and reviews.
Starting the month after the initial wiki migration, the first substantive PR
each calendar month also performs a semantic wiki review if
[the log](docs/wiki/log.md) has no review entry for that month.

## Permanent validation and implementation verification

Use extensive change-specific testing during implementation when useful. Before
merge, remove temporary tests and fixtures and record their commands/results in
the PR. Retain a permanent test only for a concrete credential, data, selected
platform compatibility, schema-conversion, or wiki-integrity risk not adequately
covered by native tools. Keep it small, deterministic, serial, and offline.

Do not require a lasting test for every behavior change. Ordinary startup,
probe, model/temperature, and app API regressions do not qualify merely by being
called compatibility checks. Do not add simulation infrastructure, tests of the
runner/toolchain, coverage quotas, disabled legacy suites, or policy inventories.
Keep runtime safeguards in operational code. Run `task fmt` and `task check`
before committing. The [validation guide](validation/README.md) lists the retained
checks and the limits of their coverage.
