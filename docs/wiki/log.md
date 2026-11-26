# Wiki log

This is the chronological record of source ingests and substantive wiki
revisions. Ordinary questions and dependency bumps do not need entries.

## [2026-11-27] revision | Suspend the public Atuin route

The Mac CLI failed its public sync at the zone TLS minimum. Removed the Atuin
tunnel origin before withdrawing its DNS record and retained its Access policy.
Karakeep passed its public token and isolation checks.

## [2026-11-27] revision | Publish Karakeep and Atuin through Cloudflare

Enabled both proxied tunnel records after verifying connector readiness, client
policy enrollment and the two Envoy header filters.

## [2026-11-26] revision | Stage authenticated Cloudflare access

Added the outbound connector, per-app Access configuration and staged DNS
controls for Atuin and Karakeep. The connector page covers credential delivery,
remote acceptance and rollback.

## [2026-11-25] revision | Automate kubelet serving-certificate trust

Enabled Talos serving-certificate rotation and a scoped kubelet CSR approver.
VictoriaMetrics and metrics-server trust the mounted Kubernetes cluster CA,
replacing the temporary kubelet CA pin and the metrics-server verification
bypass. Documented initial migration, automatic renewal and diagnosis in the
bootstrap, monitoring and app pages. Added the approver to the index and a
small credential-scope check. Foundation installs the approver before reading
storage observer logs so a fresh node can obtain its first serving certificate.
November's semantic review is already recorded below.

## [2026-11-25] revision | Retire an unused selfhosted application

Removed the application definition, dedicated credential mapping and app page,
its Restic mount and exclusions, and application-specific SQL recovery paths.
Simplified first-handoff evidence to verified file restores or checksum-verified
retained data. Updated the backup, GitOps, storage, validation, index and source
explanations and removed retired application references from this log. Git history
retains the original records. November's semantic review is already recorded below.

## [2026-11-24] revision | Let Tuppr own Talos and Kubernetes upgrades

Added the Talos target beside Kubernetes and made bootstrap generation consume
both manifests. Removed both manual upgrade commands, their playbooks and
upgrade-only helpers, defaults and version overrides. Talos uses Tuppr's native
single-node behavior without custom backup or storage checks. Renovate groups
the target and Factory installer for patch updates as well as release changes;
patches and minors automerge, while major upgrades and downgrades need review.
Updated Tuppr operations, bootstrap, the installer
decision, Renovate, contributor and validation explanations. Reviewed README,
source catalog and recovery pages; their bootstrap and recovery links remain
accurate. November's semantic review is already recorded below.

## [2026-11-24] revision | Clean up implementation artifacts

The [agent workflow](agent-workflow.md#developer-loop) links the repository's
rule for temporary files. Gateway foundation no longer queries the retired
`gateway-api` Application.

## [2026-11-23] revision | Replace Istio and consolidate Gateway API ownership

The [gateway](apps/platform-system/envoy-gateway.md) manages the shared ingress
proxy. Its [CRD chart](apps/platform-system/envoy-gateway-crds.md) supplies the
standard Gateway API to both GitOps and foundation. Documented the direct LAN
listener, certificate ownership, and recovery checks.

## [2026-11-23] revision | Recover storage and kubelet monitoring

Refreshed the public kubelet CA after its self-signed serving chain changed.
The [VictoriaMetrics page](apps/platform-system/victoria-metrics.md) explains
upgrade checks, trust reload and the remaining manual renewal requirement.
The [storage maintenance page](apps/kube-system/storage-maintenance.md)
documents initializing the scheduled SMART job and distinguishing test
initiation from completed device self-tests.

## [2026-11-22] revision | Prefer energy efficiency on the Ryzen host

The [Talos runbook](architecture/talos-bootstrap.md#cpu-power-preference)
covers the CPU energy preference and how to verify or roll it back.

## [2026-11-22] revision | Retire the status hostname

The [monitoring runbook](architecture/uptime.md) points directly to the
authenticated Grafana uptime dashboard after removal of the redirect route.

## [2026-11-22] revision | Discover routed uptime probes from Services

VictoriaMetrics now discovers application URLs from their owning Services.
The [monitoring runbook](architecture/uptime.md) covers onboarding, target
withdrawal and verification. Infrastructure and external probes remain explicit.

## [2026-11-22] revision | Declare application uptime probes on Services

The application values now declare the intended routed URL and stable uptime
identity. The [monitoring runbook](architecture/uptime.md) describes the
metadata and scoped access used to discover these Services.

## [2026-11-22] revision | Triage service, host and workload health in Grafana

The [monitoring runbook](architecture/uptime.md) explains how to follow a
Telegram alert to the affected target, distinguish a failed check from missing
samples, and investigate host or workload pressure. The affected-target table
leads on mobile, and workload rankings identify individual deployments and pods.

## [2026-11-22] revision | Transfer uptime notifications and status

The [monitoring runbook](architecture/uptime.md) covers the Grafana status
redirect to the authenticated dashboard, disabled public sharing, Telegram delivery, and reverting the cutover to restore Gatus.

## [2026-11-22] revision | Retire the temporary telemetry storage class

[PR #521](https://github.com/edgard/home-ops/pull/521) moved both databases to
standard appdata. The [namespace backup](apps/platform-system/platform-system-backup.md)
and ordinary retained PVCs now provide their recovery paths.

## [2026-11-22] revision | Move telemetry to standard appdata and Restic

The [storage architecture](architecture/storage.md#local-telemetry) and
[backup runbook](operations/restic-backup-restore.md) cover the default class,
snapshot-based backup and platform namespace recovery.

## [2026-11-22] revision | Stage local Grafana monitoring

Documented [parallel probe comparison and cutover](architecture/uptime.md),
Talos host and workload metrics, and the [local telemetry storage class](architecture/storage.md#local-telemetry).

## [2026-11-21] revision | Consolidate operator setup and recovery entry points

The README links each install or recovery scenario to its procedure. The
[agent workflow](agent-workflow.md#local-setup) owns local tool setup, and
the root contributor rules link to the detailed review and testing policies.
The [backup runbook](operations/restic-backup-restore.md#offsite-copy-and-retention)
distinguishes the daily B2 copy from weekly local retention. The
[networking page](architecture/networking.md#find-the-node-on-the-lan)
explains how to look up the node and which DNS server handles each name.

## [2026-11-21] revision | Serve shared datasets over SMB

Documented the file server in the existing selfhosted namespace, explicit ZFS mounts, LAN listener and
guest identity for Samba. Cold recovery also checks for direct pool writers.
The [Samba page](apps/selfhosted/samba.md) covers access and verification.

## [2026-11-21] revision | Verify restore coverage and coordinate manual upgrades

The [Restic runbook](operations/restic-backup-restore.md) explains how a full
restore checks each claim and its owner against the chart render. It also
shows when to snapshot the quiesced datasets before replacing their contents.
The [Tuppr page](apps/platform-system/tuppr.md) documents the committed
Kubernetes target and the suspension required for a manual upgrade.

## [2026-11-21] revision | Install Talos and recover OpenEBS appdata

Replaced source staging and SSD imaging procedures with Talos pool enrollment,
OpenEBS claim provisioning and Restic recovery before workloads start.
Documented which data comes from namespace backups and which needs a native
PostgreSQL restore. Restic records the verified destination for each ordinary
claim automatically. Renovate uses the published Talos installer-base tags
and the deployed Talos support matrix for Kubernetes proposals.
The original storage procedure is preserved in the
[previous repository revision](https://github.com/edgard/home-ops/tree/e0ffdb032870a9272c7abd691788e9b4e4b48ee1).

## [2026-11-21] revision | Start Paperless-GPT as its data owner

Documented how the GPT container uses the existing Paperless data ownership
on OpenEBS. Validation compares its rendered process identity with the user
and group configured for Paperless.

## [2026-11-21] revision | Render Renovate CRDs before its first job

Documented how the operator chart exposes its CRDs to Argo CD during a fresh
installation and how that affects later CRD ownership. Kubernetes validation
now checks the RenovateJob against the same chart schema.

## [2026-11-21] revision | Restore and verify appdata on Talos

Documented how migration exposes the held snapshot read-only for kubelet,
checks source SELinux labels, preserves destination labels and compares claim
contents and metadata. Handoff detaches the verified snapshot after the final
comparison. Subsequent checks verify every current app claim and its binding.

## [2026-11-21] revision | Install Gateway API before Argo CD

Documented how foundation installs the GitOps-owned standard bundle and waits
for HTTPRoute discovery before Helm creates the Argo CD server route.

## [2026-11-21] revision | Run appdata on bare-metal OpenEBS

Split foundation and GitOps handoff. Documented local dataset bindings,
snapshot-based claim migration, namespace backups and guarded restores,
storage monitoring, and bare-metal lifecycle checks. Added a headless rescue
USB route for capturing and reimaging an installed SSD over the LAN.
Updated the cutover to Talos 1.14, including the new configuration documents
and an unattended install selector tied to the SSD's stable path and serial.
Documented rescue with the HDDs attached, a guarded first Talos apply and
the verified four-partition discovery scope for subsequent boots.

## [2026-11-21] revision | Stage a cold TrueNAS migration

Added operator tasks and a runbook for preserving the source appdata, shared
datasets and original system disk before installing Talos on the same machine.

## [2026-11-14] revision | Simplify Renovate dependency discovery

Moved supported CI tool pins and the Talos bootstrap image to native discovery
and consolidated annotated pins into one regex manager. The ApplicationSet chart
inputs keep their own matcher. Updated the Renovate Operator and Talos installer
pages. November's semantic review is already recorded below.

## [2026-11-13] revision | Keep Helm image tags and digests together

Removed duplicate Renovate extraction for Helm values and documented combined
tag-and-digest image pins.

## [2026-11-09] revision | Focus Renovate manual review on operational changes

Enabled PR automerge for scheduled lockfile refreshes, digest pins, and major
updates to the CI actions and validation tools exercised by the Quality Gate.
Kept manual review for other majors and Gateway API updates, and made review
explicit for Kubernetes and Talos release-line changes and downgrades. Reviewed
the Renovate, validation, Terraform, Talos, Tuppr, and Gateway API explanations.
November's semantic review is already recorded below.

## [2026-11-08] revision | Record CrossWatch tracker data migration

Reviewed the non-major dependency update after the validation simplification.
Recorded CrossWatch's upstream automatic JSON-to-database migration, retained
JSON recovery copies, and changed internal snapshot defaults in its app page.
The config PVC and deployment wiring remain unchanged. Reviewed the Renovate,
validation, and Paperless explanations; existing compatibility restrictions
remain accurate. November's semantic review is already recorded below.

## [2026-11-08] revision | Retire simulated lifecycle validation

Removed permanent lifecycle/fake-API/fake-CLI simulations, parallel rendering
coordination, harness/installer tests, mutation matrices, and ordinary app
startup/probe/feature contracts. Native all-app Helm/schema/deprecation validation
remains required through a serial adapter; small offline checks retain the
credential, data, platform compatibility, schema-conversion, and wiki-link risks.
Adapters and test files share one validation directory. Runtime safeguards and
deployed configuration remain unchanged. CI Tests no longer installs operator
CLIs or Ansible collections. Contributor rules now distinguish extensive temporary
implementation verification from justified minimal permanent checks. Updated
related validation, secret, bootstrap, storage, uptime, and recovery explanations
and removed stale test links. November's semantic review is already recorded below.

## [2026-11-07] revision | Resume normal Restic scheduling

Removed the temporary retirement pause from backup and maintenance CronJobs and
removed its temporary operational note. Daily and weekly schedules, retention,
and the existing file-based restore procedure remain unchanged. Historical
application retirement records remain in this log.

## [2026-11-07] revision | Retire Sure

Removed the independent application definition, app-only tests, route monitoring,
and SQL-specific backup/recovery instructions. Restic backup and maintenance are
explicitly suspended for the retirement's storage cleanup and selective historical
snapshot rewrite; the follow-up change restores their original schedules and policy.
Dedicated credentials and retained live storage are removed operationally. Existing
whole-appdata NAS snapshots remain under their normal seven-day retention by choice.
Shared OpenAI credentials, other applications and historical Git/wiki records remain.
Reviewed backup architecture, recovery runbook, application index and source catalog.

## [2026-11-07] revision | Explain Gateway API downgrade protection

Verified the vendored CRDs against the canonical upstream standard bundle and
documented its admission-policy downgrade boundary. A Git revert may initially
be rejected by the active bundle-version floor; plan the policy change explicitly
while preserving stored custom resources and coordinating GitOps. Reviewed Istio and networking explanations;
their existing controller and route contracts remain accurate. November's
semantic review is already recorded below.

## [2026-11-07] revision | Enable native AI in Sure

Wired Sure web and worker to the existing Bitwarden OpenAI credential with shared
model and request budgets. Documented native account/family switches and hosted
document retrieval. No additional services or backup framework are introduced.
Reviewed the app page against the versioned upstream provider implementation.

## [2026-11-07] revision | Preserve application contracts during major upgrades

Retained the compatible Gotenberg API major, updated to its final security
release, and constrained Renovate until Paperless's bundled conversion client
supports the replacement request fields. Explicitly disabled Unpackerr's new
default HTTP listener while retaining secret-backed Sonarr/Radarr configuration.
Added compatibility and rendered-listener regression checks; documented the
Paperless upgrade gate and Unpackerr's headless, nonpersistent configuration.
Reviewed Karakeep, networking, storage and validation explanations; they remain
accurate. November's semantic review is already recorded below.

## [2026-11-07] revision | Verify shell programs

Corrected Sure's temporary-directory startup and preserved shell programs as
literal YAML blocks. Executable command tests cover Redis launch, dump publication,
failure cleanup and seven-generation retention. November's semantic
review is already recorded below. The Kubernetes target matches the running
patch version so the temporary downgrade-prevention suspension can be cleared
without scheduling node maintenance.

## [2026-11-07] review | November semantic review and standalone Sure

Compared the restored baseline explanations with current source metadata,
application values, NFS storage, ESO delivery, Gateway/Gatus routes, Restic
capture/restore and validation contracts. The abandoned shared-service
architecture is absent. Existing application explanations still describe their
app-owned storage; no existing database migration is enabled.

Added Sure with its own PostgreSQL/Redis, native startup and app-local SQL dumps.
Updated backup/recovery and source/index links to explain dump-based recovery
and raw-engine exclusions. Clarified k8tz's official chart source and Tuppr's
native suspension boundary for older restored version targets. Retained the
compatible Meilisearch engine so its existing datastore remains readable; no
index/data deletion is part of the rollback. Home Assistant also retains its
compatible release because its newer HTTP-settings storage format cannot be
opened by the older image. Reviewed secrets, storage,
networking, validation and uptime pages; their remaining contracts are accurate.

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
