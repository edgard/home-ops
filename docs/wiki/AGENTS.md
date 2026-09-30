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

## Query

1. Start at [the index](index.md), then read the relevant wiki pages and their
   cross-references. Use [the source catalog](sources.md) when locating broader
   evidence.
2. Follow source links to current configuration and policy for current facts.
   Check a cited merged PR or commit for historical reasoning. If sources
   disagree with the wiki, report the discrepancy instead of repeating the
   stale claim.
3. Answer with source links and mark unsupported conclusions as `Unknown` or
   `Inference`. File a reusable finding or new connection through a PR when it
   would improve future answers. Log the filed result, not every chat question.

## Ingest

1. For a new tracked source, substantive repository change, or relevant merged
   PR, read the source and compare it with the affected wiki pages. Git commits
   and merged PRs preserve immutable snapshots of otherwise changing repo files.
2. Update all affected explanations and cross-references, including
   contradictions and unknowns. Update the index for new or renamed pages, the
   source catalog for new evidence areas, and the log for the ingest or
   substantive revision. Keep current settings linked to their owning files.
3. Review the page evidence, then run `task lint:wiki` and `task lint` before
   committing. Make the wiki revision part of the same PR as a substantive
   source change. A routine version bump needs no wiki edit if no claim changes;
   state which pages were checked in the PR.

## Review

Beginning the calendar month after the initial migration, the agent preparing
the first substantive repository PR each month owns a semantic wiki review.
Check [the log](log.md) first; if it already records a review for that month,
do not repeat it. If no substantive PR occurs, perform the review during the
next one rather than creating a PR solely for a calendar reminder.

Compare page claims with sources changed since their reviewed commits. Look
for contradictions, stale explanations, orphan pages, missing cross-references,
important topics without pages, and evidence gaps. Propose corrections in the
same PR and record the review and its findings in the log, including a
no-change conclusion. Running structural lint alone does not count as a
semantic review.

The checker covers structure and local links, not the truth of prose. PR
review decides whether the source still supports an explanation.

Never ingest private chats, agent memory, ignored operator files, decrypted
Vault contents, credentials, or unsanitized runtime logs. Live checks can
validate a current claim but changing runtime status does not belong in the
wiki. Preserve operational safety instructions when editing runbooks.
