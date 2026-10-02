# Wiki log

This is the chronological record of source ingests and substantive wiki
revisions. Ordinary questions and dependency bumps do not need entries.

## [2026-09-30] ingest | Initial repository migration

Recorded the `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b` source baseline,
moved the agent guidance and Restic runbook, and added architecture, decision,
and all current app pages from tracked files and relevant merged PRs. The source
catalog and Ansible structural check describe the maintained corpus.

## [2026-09-30] revision | Make wiki workflows default

Root agent instructions now start repository questions at the wiki index and
require wiki-impact review for substantive changes. The wiki rules spell out
query, ingest, and semantic review steps; the PR template records which pages
were checked. The first substantive PR in a calendar month owns a semantic
review when no review is logged that month. Routine version-only updates
remain free of prose churn.

## [2026-10-02] review | October semantic review and Renovate path repair

Compared the tracked wiki's source links and claims with source changes since
their reviewed commits, through `9b6b7afd758013ef4288ed68b10f088053661e07` and
the current repair. The intervening app, provider, and tool version updates do
not change the architecture, storage, routing, backup, or credential explanations.
Checked the app catalog and cross-references for orphan pages and missing topics.

The Talos role-defaults move left Renovate pointing at the former `vars` path,
so only the bootstrap installer was updated. Corrected that file pattern and
aligned the upgrade default with the patch, retaining the existing upgrade
contract that caught the mismatch. Reviewed all Renovate managers, dependency annotations,
package rules, and the Gateway API CRD update hook against current files.
Expanded the Renovate Operator and Talos installer pages and added dependency
maintenance to the source catalog. The audit also found that the intended
Terraform CLI exclusion covered only `.terraform-version` files, leaving the
manually managed OpenTofu `required_version` constraint eligible for Terraform
updates. Extended the exclusion to that dependency in Terraform configuration
while preserving provider and CI OpenTofu updates. No additional moved-path gaps
were found; unchanged pages retain their prior reviewed commits. Structural
validation remains separate from this review.
