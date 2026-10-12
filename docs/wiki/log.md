# Wiki log

This is the chronological record of source ingests and substantive wiki
revisions. Ordinary questions and dependency bumps do not need entries.

## [2026-10-12] revision | Unify validation under pytest and native tools

Replaced Conftest/Rego, configuration inventories, static operation catalogs,
nested test runners, and production test-mode branches with direct source
assertions and real role/Task scenarios. Native validators retain their specialized
checks. Kubernetes rendering now accepts a caller-owned private workspace; pytest
checks sources first, shares output once, and owns cleanup. CI and local commands
cover disjoint pytest subsets. Reviewed contributor guidance, validation/decision,
bootstrap, secrets, recovery, storage, uptime, source catalog, and related decisions.
October's semantic review is already recorded below. Earlier entries describe the
historical architectures superseded by this revision.

## [2026-10-12] revision | Separate repository policy from behavior fixtures

Moved static role safety, application wiring, credential ownership, Talos target
compatibility, validation wiring, and Gatus coverage decisions into their policy
layers. Validation roles collect inputs and invoke Conftest; native Git artifact
lint and disposable execution/parser/rollback/check-mode fixtures remain distinct.
Added a policy boundary guide and `lint:repository`, wired into full lint and the
Ansible CI job. Reviewed the contributor workflow, validation architecture and
decision, recovery transaction, Talos installer, and uptime pages. The October
semantic review is already recorded below.

## [2026-10-12] revision | Harden Ansible operator conventions

Guarded confirmed Restic restores and pod exec tasks in check mode, changed
Talos upgrade verification to compare the selected server's tag exactly, and
unified SecretSpec installation and validation around the role pin. Added
operator-tool Renovate discovery and refactored role contracts to preserve
operational guarantees without depending on absolute task positions or counts.
Reviewed recovery, bootstrap, secret maintenance, validation, and Renovate wiki
pages. The October semantic review is already recorded below.

## 2026-10-11 — Restore Ansible ownership of secret workflows

Corrected the unified-secret implementation to follow the existing playbook/role
pattern: native setup, preflight, generation, handoff and token rollback; direct
native SecretSpec launch with inherited-credential cleanup; role-owned adapter
and focused Ansible fixtures. Retired the completed state-migration helper and
its exclusive tests, retaining protected backups and immutable recovery history.
Reviewed the secrets runbook, bootstrap, validation architecture, contributor
workflow and README against the implementation.

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

## [2026-10-11] revision | Unified Bitwarden secret delivery

Updated secret ownership, scoped Task commands, deterministic Talos generation,
preflight and ESO/Argo handoff, Terraform variables/state retirement, and token
replacement. Added the provisioning/migration runbook and marked the former
operator-environment decision historical with immutable links. Reviewed related
bootstrap, GitOps, backup, validation, Terraform, and External Secrets pages.
The October semantic review is already recorded above. Real cloud migration and
retirement of the encrypted recovery input require the runbook's acceptance steps.

## [2026-10-11] revision | Verify infrastructure item names and ownership

Checked existing Bitwarden item metadata without exposing values. Corrected
SecretSpec's Tailscale references to match the deployed ESO item name and moved
operator-exclusive zone/OAuth client identifiers to the operator alias. The
migration runbook retains originals for round-trip verification, then requires
their retirement so values do not remain duplicated between projects.

## [2026-10-11] revision | Gate state retirement on infrastructure preflight

The state migration helper now checks a private temporary plan before remote
state writes and rejects managed-resource changes. It still verifies the recovery
backup, removes only the known retired data entries, checks managed state equality,
and requires a zero-change final plan. Updated the migration runbook accordingly.

## [2026-10-11] revision | Reuse the shared read-only machine account

Configured the operator project's public UUID and reused the existing machine
account for both project reads. Updated preflight to enforce the configured
project set, and documented that command scopes control injection while ESO's
credential can read operator secrets too. Reviewed setup, rotation, retirement,
the architecture pages, External Secrets, the README, and contributor guidance.

## [2026-10-11] revision | Preserve zero-change infrastructure migration

Preserved legacy resource-state zone-ID sensitivity while keeping the operator
input nonsensitive. Added a Cloudflare provider compatibility pin and Renovate
limit for the query-parameter regression. The isolated official-provider plan
has no managed-resource changes; DNS attributes, addresses, and backend remain
unchanged. Reviewed the Terraform architecture and state-retirement runbook.

- 2026-10-11: Revised Kubernetes validation to use served CRD schemas from pinned charts and tracked manifests before catalog fallback; retained strict field checks and added malformed, conflicting, and invalid-resource regression coverage.

## [2026-10-11] revision | Retire legacy secret maintenance

Retired the encrypted Talos Vault file, one-time migration verifier, Vault-only
formatter/linter exceptions, and retained-Vault contract. Added regression checks
that reject active legacy maintenance and protect credential backups. Updated
contributor guidance, README, architecture, and maintenance/recovery instructions;
preserved the migration procedure and historical decision with immutable links.
