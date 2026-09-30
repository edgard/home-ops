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

- Configuration and policy are the source of truth; verify wiki claims against
  the current files and, when relevant, the running system.
- For behavior changes, write or update a failing policy or contract check first.
- Run `task fmt` and `task lint` before committing or updating a PR.
- Argo CD sync follows a committed and pushed GitOps change; do not sync local
  uncommitted configuration.
- Keep credentials in the existing ignored operator environment or encrypted
  Vault file. Never copy secrets into the wiki.
