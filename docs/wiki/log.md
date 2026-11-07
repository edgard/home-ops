# Wiki log

## 2026-11-07 — Align cold restore's outer test allowance

Removed the cold restore scenario's older, shorter subprocess ceiling so it
uses the shared whole-role allowance. Hosted CI reached that ceiling during
identity-checked state restoration; production timing and safety checks remain
unchanged. Clarified that cold fixtures omit default ServiceAccounts and
corrected the Restic page's reviewed revision to its published source.

## 2026-11-07 — Keep cold ServiceAccounts explicit

Separated the ordinary executor fixture's default ServiceAccount from cold
bootstrap fixtures. Cold scenarios retain explicitly supplied foreign resources;
the production ownership checks remain unchanged. Native cold rendering remains
part of the full gate before operations delivery.

## 2026-11-07 — Refresh rollout against merged dependencies

Incorporated the separately merged dependency update before operations delivery.
Temporary recovery-engine pins and disposable native checks now use the same
PostgreSQL and Redis images as the shared service manifests. Existing migration
rehearsals must be refreshed against the currently deployed application versions
before any private-data cutover.

## [2026-11-07] revision | Isolate fixture Git repositories

Clear inherited Git context before pytest starts fixtures or workers. A real
nested-run regression exercises repository creation and removal while checking
that an outside repository's configuration, index and files remain unchanged.
Updated the test guide and validation architecture.

## [2026-11-07] revision | Fence original nodes and shared engine reconciliation

Ordinary maintenance now records the native authenticated coordinator's original
node name and UID, and checks historical node identity before recovery fencing
and its absence barrier. Missing bindings and same-name replacements stay held.
Every operation also holds the independent PostgreSQL and Redis Applications
without stopping their server workloads or treating raw engine storage as
application files. Automatic sync is disabled before in-flight work drains;
fresh identity/version guards then skip idle reconciliation. Resumption restores
original policies and skip annotations with root last and refuses queued manual
syncs. Partial-resume compensation preserves foreign requests while re-holding
all remaining targets and writers; interrupted enrollment checks the same holds
before native producer or route restoration. Updated shared-data, PostgreSQL,
Redis, operations infrastructure and Restic
explanations against the public base and current role sources. Frozen operator
images still require compatible inventory/code before activation; adoption and
operation schedules remain paused. November's semantic review is recorded below.

## [2026-11-07] revision | Bind cold bootstrap to a real fenced executor

Documented a suspended, digest-pinned Job claiming the shared maintenance Lease
and durable journal before grants or platform mutations. Actual bound-token Pod
identity, source assets, runtime code, deleted-resource refusal, exact old-worker
fencing, and restore/admission registry checks now define the held recovery
boundary. Updated the [shared-data procedure](operations/shared-data.md),
[Talos architecture](architecture/talos-bootstrap.md), and [Restic runbook](operations/restic-backup-restore.md).
Executable runtime admission remains a separate mandatory activation blocker.
November's semantic review is already recorded below.

## [2026-11-07] revision | Bound CI failure queues and expose case names

The expanded native test suite reached the job budget after a failure while
other workers drained previously assigned work. CI now uses a lower worker
limit, bounded load queues, verbose case names and a larger overall job budget.
An executable subprocess regression proves early failure leaves most unrelated
cases unstarted and a successful invocation still executes every case. Updated
the validation page, contributor workflow and test guide; local defaults and
production operation deadlines remain unchanged.

## [2026-11-06] revision | Add held Paperless enrollment

Documented bounded operator sessions, source and actor identity checks, draining
the original Pod before the separate shutdown-template merge, application at
zero replicas, and source-aware resume/abort. Added the
[enrollment runbook](operations/paperless-enrollment.md) and updated the
shared-data and Paperless pages. This supplies tooling; production enrollment
and database cutovers remain separate acceptance steps.

## [2026-11-06] revision | Guard native operation scopes and preserve repository-wide retention

Native backup and provisioning now reject file-only or mixed file/native scopes
before preview, submission, or direct coordination. Existing SQLite consumers
remain supported; restore and cleanup retain combined scope. Updated the
[shared-data procedure](operations/shared-data.md).

Restored retention across every repository family, including workstation
documents, while explicitly keeping all pending uploads for separate inspected
cleanup. Updated the [Restic page](apps/selfhosted/restic.md) and
[backup runbook](operations/restic-backup-restore.md). Native Restic regressions
cover both workstation hosts, consumer scope groups, future families, and old
pending snapshots that would otherwise expire. November's semantic review is
already recorded below.

## 2026-11-05 — Shared database startup corrections

- The NAS passed setgid to the empty new PGDATA directory, so the strict startup
  check refused it. Normalize only an empty UID/GID999 directory and retain the
  existing-data refusal. Native tests cover inherited setgid, restart persistence,
  and unchanged nonempty data on refusal.
- Reject linked PGDATA paths before changing permissions. Correct Redis probes
  to use the pinned CLI's supported host flag and test successful authentication
  with the exact deployed commands.
- Updated the [PostgreSQL](apps/platform-system/postgresql.md) and
  [Redis](apps/platform-system/redis.md) pages; related shared data/storage
  explanations remain accurate.

This is the chronological record of source ingests and substantive wiki
revisions. Ordinary questions and dependency bumps do not need entries.

## [2026-11-04] revision | Prepare shared PostgreSQL, Redis, and maintenance infrastructure

Added the shared-service definitions, retained claims, independent administrator
and consumer credential delivery, and paused operations templates. Added service
and operations app pages, internal TCP monitoring, the inactive backup heartbeat,
the home-automation secret-store allowance, and the bounded cross-namespace
AppProject/RBAC explanation. Excluded database persistence and staging from
legacy file capture and destructive restoration. Documented ownership/bootstrap
and connection-budget constraints, including Sparky's separate authentication
pool. Added startup/restart, scope, exclusion, and digest-discovery checks.
November's semantic review is recorded below; application cutovers remain later
stages.

## [2026-11-04] review | November semantic review and shared-data foundation

Reviewed all application pages, architecture, decisions, and operations against
their current owning sources and source changes since their recorded reviews.
Corrected the claim that sync-wave annotations on independent ApplicationSet
children enforce cross-application readiness. Documented the legacy restore
role's root self-heal limitation and the distinction between its deployed path
and the new root-aware maintenance foundation. Added the staged shared-data
operations topic, registry/image sources, secrets/storage/controller
cross-references, required disposable native database/Restic tests, and the
separate operations-image build gate.

Repaired k8tz's chart source using its official upstream repository while
retaining the pinned chart version. Reviewed app dependencies, persistent-data
boundaries, media ownership, networking, explicit Gatus targets, Bitwarden
delivery, Talos bootstrap, Terraform, Paperless AI recovery, and dependency
maintenance. Their remaining explanations match current sources; intervening
version changes do not require prose updates. App definitions and pages remain
paired, with no orphan applications. The foundation stage does not represent a
shared-service deployment or an application migration.

## [2026-10-27] revision | Bound Paperless cold starts and index recovery

Extended the main container startup-probe budget for cold AI initialization while
retaining readiness gating. Added a rendered-probe regression. Updated the AI
recovery procedure to drain native indexing tasks before a final manual refresh:
queued jobs carry earlier document snapshots and can replace newer index entries.
Separated persistence checks from freshness checks and retained source review of
generated document labels. October's semantic review is already recorded below.

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

## 2026-11-05 — Shared data orchestration and recovery

Updated the shared-data procedure, Restic runbook, backup architecture, restore
decision, and affected app pages against the new role-owned backup/upload/restore
and API-only monitoring paths. Documented root-first maintenance, immutable
generations, capture-time freshness, manifest-bound selective recovery, compatible
Restic commands, and the published-image/adoption gates. November's semantic
review was already recorded with the foundation; this is its follow-up ingest.

## 2026-11-06 — Native fixture ownership and CI diagnostics

Aligned bind-backed adapter clients with their test coordinator's numeric
identity so Linux can inspect and clean private artifacts without loosening
production permissions. Dedicated root/server ownership and capability fixtures
retain their explicit profiles. Updated the test guide and made CI stop after a
failure so its diagnostic report is emitted before a later job timeout.

## 2026-11-07 — Recovery scenario timing and fixture cleanup

The first bounded CI failure report identified an outer backup-test timeout
during resumption after capture. Increased whole-scenario and CI allowances for
native recovery cases without changing production pause limits or safety
assertions. Added coordinator-exit cleanup coverage for waiting upload workers.
Reviewed the validation architecture and test guide against the actual CI trace.
The subsequent Linux report reached final Lease release during pending-snapshot
cleanup before its shared role-runner limit expired. Applied the same whole-role
allowance consistently, preserving explicit short timeout and child-cleanup tests.

- 2026-11-07: Registered native Talos/platform operations now share maintenance
  exclusion with data and cold recovery. Documented explicit local ownership,
  positive fresh-state proof, source-adopted coordination namespace retention,
  and manual-only resolution of interrupted native work. Updated the Talos
  architecture and shared-data operation runbook against the scoped source.

- Corrected native-operation exclusion to durably fence automatic Tuppr execution, preserve minimal GitOps state, restore Root last, and model deletion-only Argo finalization and fresh composed handoff.
