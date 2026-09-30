# Home Ops

This is a single-node Talos and Argo CD GitOps repository. Make changes on a
branch through a pull request; never commit directly to `master`.

Before changing the repository, read [the detailed workflow](docs/wiki/agent-workflow.md).
For wiki edits, also read [the wiki conventions](docs/wiki/AGENTS.md).

- Configuration and policy are the source of truth; verify wiki claims against
  the current files and, when relevant, the running system.
- For behavior changes, write or update a failing policy or contract check first.
- Run `task fmt` and `task lint` before committing or updating a PR.
- Argo CD sync follows a committed and pushed GitOps change; do not sync local
  uncommitted configuration.
- Keep credentials in the existing ignored operator environment or encrypted
  Vault file. Never copy secrets into the wiki.
