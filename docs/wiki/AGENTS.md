# Wiki maintenance rules

The wiki is an agent-maintained explanation of this repository, reviewed through
the same pull requests as code. Repository configuration, policy, and operational
tasks remain authoritative. Read [the agent workflow](agent-workflow.md) before
changing deployment behavior.

## Page contract

Every content page except the index, log, and source catalog must have:

- A short purpose statement and `Status: current` or `Status: historical`.
- `Reviewed against: <commit>` for the repo state checked when writing it.
- A `## Sources` section with links to current repository files, merged PRs, or
  commits. Link an unusual or historical claim near that claim as well.
- A `## Related pages` section with wiki links, or `None` if no relationship is
  established. Mark unsupported rationale as `Unknown`; mark a reasoned claim
  that is not directly stated by a source as `Inference`.

Use repository-relative Markdown links so the offline checker can verify local
targets. Link current settings to their owning manifests or tasks instead of
copying versions, schedules, endpoint inventories, or live health. Historical
reasons need a merged PR or commit citation. External documentation is linked,
with a short relevance note; do not copy its contents into this public repo.

An app page lives at `apps/<category>/<app>.md` for every
`apps/<category>/<app>/app.yaml`. Explain purpose, dependencies, storage and
recovery implications, networking and monitoring, and any special constraint.
State `Unknown` where the sources do not support a conclusion. An app page is
not a generated dump of Helm values.

## Ingest, query, and review

1. Read [the source catalog](sources.md) and the relevant current files first.
   For historical reasoning, inspect the linked merged PR or commit.
2. Update affected pages, their links in [the index](index.md), and
   [the log](log.md) when an ingest or substantive revision occurs. A useful
   query result becomes a page only through a PR; ordinary questions do not
   create log entries.
3. Run `task lint:wiki` and `task lint`. Review prose against sources in the PR.
   The checker covers structure and links, not semantic truth.
4. Periodically review changed sources, contradictions, orphan pages, and
   evidence gaps. Propose corrections by PR.

Never ingest private chats, agent memory, ignored operator files, decrypted
Vault contents, credentials, or unsanitized runtime logs. Live checks can
validate a current claim but changing runtime status does not belong in the
wiki. Preserve operational safety instructions when editing runbooks.
