# Wiki log

This is the chronological record of source ingests and substantive wiki
revisions. Ordinary questions and dependency bumps do not need entries.

## [2026-10-27] revision | Enable Paperless native AI and bounded enrichment

Enabled native AI generation and multilingual embeddings using the existing
credential and persistent data volume. Disabled GPT document-type generation,
preserved existing metadata, and enabled clean digital-page reuse. Documented the
saved custom-field and prompt setup, import/enrichment workflow boundaries,
provider canaries, failure recovery, conservative reference-link review, and native
chat/index limitations. Added configuration safeguards and the AI operations
procedure. Kept reference-link writes in review mode because the current upstream
lookup examines only one substring-match page. Reviewed storage, secrets, and backup/recovery explanations; their
existing claim-based contracts remain accurate. October's semantic review is
already recorded below.

Separated PDF/image OCR routing from all-document enrichment so converted Office
documents retain Tika's digital text instead of being unnecessarily re-OCRed.

The local gate also exposed a reverse-DNS dependency in the synthetic loopback
Kubernetes server. Bound its server name directly to the loopback address and
added a regression with reverse DNS unavailable; fixture startup no longer waits
on an external resolver. This changes test infrastructure, not cluster behavior.

## [2026-10-23] revision | Restore Karakeep startup after image upgrade

Restored the main container's `CHOWN` capability so its root s6 entrypoint can
adjust the newer image's `/run` ownership. Kept default capabilities dropped,
privilege escalation disabled, and the browser/search security profiles intact.
Extended the rendered-resource entrypoint contract to cover Karakeep and added
missing-capability regression cases. Updated the Karakeep operational note;
reviewed networking, uptime, and storage explanations, which remain accurate.
October's semantic review is already recorded below.

## [2026-10-18] revision | Repair Paperless GPT document processing

Bound OCR image rendering for the provider's image limits, configured the vision
temperature explicitly, selected a metadata model supported by the bundled
client, and removed the partial-document OCR page cap. Persisted GPT settings,
prompts, and history on the existing Paperless claim. Updated the Paperless page
with client compatibility, saved-setting precedence, original-file preservation,
and failed-document recovery. Reviewed storage and backup/recovery explanations;
their claim-based contracts remain accurate. October's semantic review is
already recorded below.

## [2026-10-17] revision | Standardize validation commands and CI

Separated formatting, static analysis, pytest, and the complete `task check`
gate. Replaced duplicate YAML formatting with yamlfmt, added Ruff and bundled
configuration schemas, and moved Python dependency setup to locked uv sync.
Tracked the root OpenTofu provider lock and preserved it through cleanup, with
read-only backendless validation and explicit OpenTofu registry maintenance.
CI now runs Format, Lint, and one complete Tests job behind Quality Gate, retaining
JUnit evidence and native installer safeguards. Scoped provider execution selects
the project interpreter even when the machine default differs. Separated synthetic
API-error budgets from deliberate timeout scenarios and reproduced slow-response
rollback coverage without changing production deadlines. Reviewed contributor/wiki rules,
test guidance, validation architecture and decision, Terraform, secrets maintenance,
source catalog, and Renovate explanations. October's semantic review is already
recorded below.

## [2026-10-16] revision | Consolidate Bitwarden storage and delivery references

Consolidated CLI and application storage around the existing application project
UUID and one SecretSpec `bitwarden` provider. ESO keeps its own direct delivery
configuration and item references. Updated bootstrap and token preflight to require
exact access to the shared project and reject project mismatches. Scope, read-only
provider, redaction, and token rollback safeguards remain in place. Updated the
secrets architecture, maintenance and migration procedure, Terraform explanation,
External Secrets page, contributor workflow, and README. Equal values across
independent service credentials do not by themselves justify merging their records.
October's semantic review is already recorded below.

## [2026-10-16] revision | Clarify CLI secrets tooling and restore role-owned pins

Renamed the local secret-delivery role and variables to `cli_secrets` and its
SecretSpec provider alias to `cli`, distinguishing CLI maintenance from Kubernetes
operators. Project UUIDs, item references, scopes, and the shared Keychain address
remain unchanged; the existing Bitwarden project display name is documented.
Removed the separate version file and restored the SecretSpec pin to role defaults,
with Renovate discovery and CI consuming the same value. The CI toolchain action
now owns its existing dependency setup and validates the staged binary before
installation. Added real-shell installer scenarios for success, checksum/version
rejection, binary preservation, and cleanup. Updated affected secrets, validation,
bootstrap, workflow, and dependency-maintenance explanations. October's semantic
review is already recorded below.

## [2026-10-16] revision | Separate machine setup from operator workflows

Retired the local operator-tool installer, its Task command, playbook, download
metadata, and installation-only tests. Local tools belong to Chezmoi/Homebrew;
CI installs SecretSpec in its toolchain action. A shared version file keeps the
CI binary and runtime validation aligned. Preserved provider, scope, version,
and credential safeguards and updated their fixtures and Renovate discovery.
Updated the README, test guide, secrets runbook, and Renovate app explanation;
reviewed the contributor workflow and secrets architecture. October's semantic
review is already recorded below.

## [2026-10-15] revision | Parallelize every pytest invocation

Added global bounded work-stealing defaults for direct pytest, Task commands,
and CI. Resource isolation remains fixture-owned, with no test eligibility
lists or scheduling exceptions. The Kubernetes fixture shares one validated
render through a bounded file lock and atomically published private snapshot;
workers receive independent objects and initialization failures block reuse.
Updated the test guide, agent workflow, validation architecture, and decision
page. Regression scenarios cover cross-module consumers, native failures,
incomplete output, terminated initializers, child-process cleanup, and isolated
loopback APIs. October's semantic review is already recorded below.

## [2026-10-14] revision | Retire BentoPDF and MeTube

Removed both app definitions and their explicit Gatus targets, app pages, and
catalog links. Kept the shared-media ownership decision and its historical PR
evidence; its rule still applies to the remaining consumers. Reviewed GitOps
delivery, storage, and uptime explanations against their current sources.
ApplicationSet deletion cascades to app-owned resources; the NFS appdata class
retains MeTube's underlying state volume, while downloaded files remain on the
shared media claim. October's semantic review is already recorded below.

## [2026-10-13] revision | Migrate Istio chart hosting

The dependency PR review reproduced Istio chart-download failures during the
upstream GCP hosting retirement test. Moved both chart sources to Istio's official
GHCR replacement while retaining their versions. Set the image hub to the
official Docker Hub source for control-plane and Gateway proxy images, and added
a rendered contract that failed against the old hub. Updated both Istio
app pages with the upstream migration evidence and checked the networking and
validation explanations. Existing rendered pytest checks reproduced the failure
before the source change. October's semantic review is already recorded below.


## [2026-10-13] revision | Keep CI Python compatible with Ansible

Reviewed the three dependency PRs against the current pytest validation layout.
The non-major group changed CI Python without updating Task's interpreter and
selected a runtime outside pinned Ansible core's support range. Retained the
supported interpreter, bounded Renovate's Python updates, and added a repository
contract for the interpreter relationship and compatibility boundary. Updated
the Renovate Operator explanation; the validation and contributor pages remain
accurate. October's semantic review is already recorded below.

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

## 2026-10-13 — Offline validation owned by pytest

Removed the remaining wiki and Kubernetes validation roles/playbooks. pytest
checks wiki sources directly and invokes Helm, served-schema export, kubeconform,
and Pluto in its own temporary workspace. Updated the validation architecture,
decision, contributor workflow, and test guide; operator runtime guards remain
in Ansible. Reviewed against `df530ab8f6edc603500f39fb634d6c404b64c636`.
