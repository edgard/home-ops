# Shared application data operations

Purpose: explain the shared-data operations foundation and rollout prerequisites.
Status: current. Reviewed against: `1b080d18e9d8e06deef71c2b8b37afda73d92c3c`.

## Delivery stage

The [rollout plan](../../superpowers/plans/2026-11-04-shared-data-services.md)
introduces shared PostgreSQL and Redis, then new applications and individually
rehearsed migrations. The first stage supplies a role-owned maintenance
coordinator, native data adapters, an operations image, and isolated tests.
Consumer cutovers and the remaining orchestration follow in later PRs. The
[registry](../../../ansible/roles/shared_data/files/registry.yaml) records intended
database ownership, connection budgets, Redis allocations, writers, file paths,
and encryption-key references. Its adoption flags remain false until each
application passes its cutover gate. Removing a registry entry does not run SQL
or delete databases, roles, or persistent files.

The [PostgreSQL](../apps/platform-system/postgresql.md),
[Redis](../apps/platform-system/redis.md), and
[operations infrastructure](../apps/selfhosted/shared-data.md) definitions now
prepare the shared services and storage. All operation schedulers remain paused
until backup/recovery orchestration is wired and accepted. Prepared consumer
Secrets do not activate application migrations. The existing daily file backup
continues for unchanged applications and excludes live database and staging
directories.

The [Restic runbook](restic-backup-restore.md) enters the database-aware
coordinator through both existing and new Task commands. The source-owned
operations image must be published and pinned before these commands or paused
schedulers are activated. Mounted registry updates supply engine Application
inventory without an image rebuild, but frozen operator images must contain the
compatible inventory and reconciliation protocol before shared-engine operations. Shared PostgreSQL consumers require database-aware
backup and recovery before activation; a file snapshot of a PostgreSQL data
directory is not the recovery contract.

## Maintenance coordination

The [Ansible role](../../../ansible/roles/shared_data/tasks/maintenance.yml)
uses a Kubernetes Lease for exclusivity and a ConfigMap journal for original
resource identities and settings. These live in the Kubernetes API rather than
on NFS. Operations require explicit confirmation, a registered scope, and a
live coordinator Pod UID. Native SelfSubjectReview must authenticate the actual
bound Pod and ServiceAccount; its nonempty unambiguous original node-name and
node-UID must match the Pod assignment and current Ready Node before acquisition.
The Lease and journal retain this original identity across ownership changes.
Recovery and cleanup compare historical node UIDs before fencing and again at
the absence barrier; a same-name replacement, missing binding, or unavailable
original node keeps ownership held. Legacy unbound claims cannot learn the
current node identity during recovery. Plan and Ansible check mode do not mutate resources.

The coordinator disables automatic sync on root and affected child Applications
before draining in-flight syncs. Fresh UID/resourceVersion checks then set
`argocd.argoproj.io/skip-reconcile` only on idle Applications, so reconciliation
is not frozen while an operation still needs its controller to finish.
A previously skipped Application with active or queued work requires inspection.
Argo's [skip-reconcile contract](https://argo-cd.readthedocs.io/en/stable/user-guide/skip_reconcile/)
stops processing and status updates; held status is not a fresh health check.
Live acceptance must verify the configured controller honors this boundary.
The ApplicationSet is held before child updates. Registered operation targets
include the independent PostgreSQL and Redis Applications for every scope,
including file-only maintenance. Their server Deployments and Pods keep running;
they are reconciliation targets, never generic application-file consumers.
The coordinator suspends registered schedules, checks node-upgrade work, and
stops selected consumer writers. Queue consumers need registered
drain checks and termination grace sufficient for active work. Original
fields, including absent policies, original skip annotations, and replica counts,
are restored with root resumed last. Before restoring writers and before each
Application is unskipped, identity and idle held-state checks refuse unexpected
queued sync requests. These requests remain for operator inspection. If one arrives during partial
resumption, compensation preserves its skip and request, re-holds the remaining
Applications, and stops resumed writers and schedules before reporting failure.
Native-only recovery of an interrupted enrollment verifies the same Application
holds before restoring producers or HTTP routes; it still cannot restore root
without the enrollment's explicit source-aware verification. Resource replacement or conflicting ownership fails closed.

For enrolled Sure and Paperless Pods, the registry supplies native producer
pause, worker quiet, idle checks, and recovery commands. The coordinator records
pause intent and Pod identity before executing them. Queued broker work remains
pending; active, reserved, and in-memory scheduled work must finish. Recovery
restarts a quiet Sidekiq worker only after idle, while Paperless can restore
native consumption and producer services on its original Pod. Missing replies
or uncertain termination keep reconciliation held.

Preflight checks the actual Pod's grace, image, and relevant settings. Updating
a Deployment template does not extend an existing Pod's shutdown grace.
Paperless's [old-Pod enrollment procedure](paperless-enrollment.md) provides a
bounded operator session across the shutdown-template merge. Publish its image
and scoped RBAC first, then hold and drain the original Pod before merging the
separate values change. Source-bound application at zero replicas and actual
new-Pod checks precede resumption. The normal capture protocol refuses an
incompatible Pod. A prepare-only hold records that writers
remain untouched. If resumption then fails, recovery preserves that boundary;
transactions that touched writers retain the stricter fail-closed behavior.

Automatic recovery is restricted to interrupted backups after the old
coordinator and its child work have been fenced. Restore, migration, and
rotation failures remain held for inspection. An independent watchdog uses
the API journal and does not require an NFS mount. API, storage, or node
failure can prevent recovery; the pause target does not guarantee downtime.

## Registered Talos and platform operation exclusion

The [native operation role](../../../ansible/roles/node_operation/tasks/main.yml)
wraps registered Talos apply, bootstrap, upgrade, Kubernetes upgrade, and reset,
ordinary platform bootstrap/removal, and composed cluster creation/removal in
the same `selfhosted/shared-data-operation` Lease and API journal. These local
commands leave ordinary application writers running. They journal and fence only
Root, the apps ApplicationSet, the Tuppr Application and its controller. Root
and Tuppr reconciliation are skipped after idle checks, the ApplicationSet is
held create-only, and Tuppr is scaled to zero. Original source and field state
are checked with UID/resourceVersion CAS before each mutation. After controller
Pods terminate, complete upgrade CR, Job and Pod inventories must prove no
active or restart-capable automatic worker remains. A preflight observation
alone does not exclude a controller launch. Only one
registered operation can acquire the gate; a held backup or cold-recovery
journal refuses native work before its first mutating command. Composed
operations acquire once, without recursively releasing between their steps.

The executor is explicitly `NativeCLI`, with a random invocation identity and
the original Ready Node UID read through the operator's Kubernetes credentials.
That is an authenticated API read, not the bound-Pod token proof used by data
Jobs. No Talos credential is copied into a Pod. The existing CLI SecretSpec scopes
and read-only Bitwarden delivery remain the same.

Lease duration covers up to twelve hours of expected API outage, but expiration
never makes native work reclaimable. Successful native completion, original-node
readiness, and applicable server-version verification precede a durable
native-critical-complete phase. Only then are exact original control fields and
annotation absence restored, with Root last, before exact UID/owner/resource-
version journal and Lease release. Restoration failure attempts each remaining
fence independently, preserving foreign queued operations and recording failures.
Failed or ambiguous native execution leaves the minimal controls fenced. A retry may wait for the same node's
API to return within that still-running invocation. A failure, lost local caller,
changed Node UID, or ambiguous API write leaves ownership held indefinitely.
The backup watchdog, administrative Pod recovery, cold recovery, and ordinary
new invocations cannot fence a local process by deleting Pods or by waiting for
TTL. There is no automated native takeover or resume command. An administrator
must separately establish that the old local process and native operation have
ended, inspect the node and preserved journal, and resolve exact retained
ownership manually. Do not clear it merely because a Pod is absent or the Lease
is old. Reset intentionally does not release after dispatch because the node/API
may be destroyed before completion can be established. Established configuration
apply also stops with ownership retained after its successful RPC: that reply
does not prove asynchronous reboot/configuration reconciliation is complete.
Established composed creation stops immediately after apply, before bootstrap
or platform mutations; a successful command is not a completed operation.

Manual finalization is an inspected administrative procedure, not a retry flag:
retain the exact Lease UID/resourceVersion, holder nonce, complete journal and
original Node UID; identify and terminate or observe completion of the original
workstation invocation and any surviving native child; independently establish
native Talos operation completion and the intended configuration/version on the
original node; verify API health, absence of in-flight native/Tuppr work, and
that no data operation acquired or changed the recorded objects. For apply,
inspect actual applied configuration and any reboot completion, not just the
RPC response or a first Ready observation. Only then may an administrator
restore only the journaled minimal upgrade-control fields after checking their
original UIDs and source specs, with Root last, using UID/resourceVersion CAS.
Do not recreate intentionally destroyed targets. Explicit UID/resourceVersion/
holder-checked journal finalization and removal of the exact native finalizers/
ownership follow successful restoration or verified destructive disposition. If any identity, old process or
node outcome is uncertain, leave both records held. No repository command
automates this judgment or supplies a blanket force unlock.

The [selfhosted namespace](../../../argocd/namespaces/selfhosted.namespace.yaml)
uses Argo's [resource retention option](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-options/#no-resource-deletion)
`Delete=false`, so platform removal retains both coordination objects while root
and application resources are deleted. Removal refuses until the actual
namespace protection and the exact successful root sync's committed source agree.
That adoption proof is journaled under the native owner before any GitOps fence
write. Deletion revalidates the original Root UID/source/revision and exact live
Namespace UID/resourceVersion/protection. Root may report OutOfSync afterward
only when resource status attributes the drift solely to the journaled apps
ApplicationSet policy change; unknown or foreign drift remains held. The root
sync must be at least five minutes old; this conservative delay is not
proof of controller-cache freshness. Exact namespace UID/resourceVersion checks
and a preconditioned root deletion precede cascade. Live acceptance must verify
the controller honors retention. A finalizer on both the native Lease and journal
preserves evidence if unexpected namespace deletion nevertheless begins; native
steps then refuse to continue. Finalizers are removed only after all successful
native work. Root DELETE is submitted without waiting while it is skipped. Only a fresh,
source-checked, exact-UID/RV Application already carrying deletionTimestamp may
have skip removed for finalizer reconciliation; this applies to Root then the
Tuppr child. Nondeleting or replaced objects are never unskipped by this path.
The workflow waits for cascade completion and verifies intended targets absent;
it never recreates them to restore old policy. Standalone platform removal
leaves the namespace and complete journal; composed cluster reset remains
destructive.

Before a Kubernetes API exists, only explicit `HOME_OPS_FRESH_CLUSTER=true`
creation can use the positive native exception. Initial apply requires native
maintenance state, a positively discovered blank configured installation disk
with no child partitions/filesystem, and no discovered STATE/EPHEMERAL storage.
Standalone bootstrap requires authenticated native evidence of EPHEMERAL mounted
at `/var`, ordinary non-symlink directory parents without a shadowing nested
mount, a successful empty `/var/lib/etcd` inventory, and a successful empty local
etcd-member resource inventory. Missing/unsupported probes or connection failures
are not empty inventories. Reachable APIs always check actual shared and cold
journals first; an existing cold journal cannot be bypassed by the fresh flag.
Composed fresh creation acquires the shared gate once its new API is available,
before any platform mutations. Ordinary platform bootstrap creates a missing
Root already skipped and without automation from the exact verified immutable
source, recording its intended policy before creation and its actual UID before
continuing. Existing Root source/policy is preserved. Missing descendants must
remain absent behind held or absent parents; an existing create-only
ApplicationSet cannot justify a missing Tuppr Application. All foundational
mutators finish and original-node completion is proved while fenced. Root is
restored last, then the read-only GitOps/Secret handoff runs under the still-held
Lease. A failed handoff retains ownership and attempts safe re-fencing; automatic
work starting after verified critical completion is not described as overlap
with an ongoing native mutation. These guards are intentionally conservative;
ambiguous native layouts require inspected recovery instead of a blanket bypass.

Direct trusted-admin Talos, Helm, or Kubernetes mutation outside these registered
entry points is outside the exclusion guarantee and must use the same maintenance
protocol. Synthetic API/native CLI tests cover ordering, crashes and ownership;
they do not authorize or demonstrate a live upgrade, reboot, reset, or removal.

## Cold infrastructure recovery and admission boundary

The [dedicated platform playbook](../../../ansible/playbooks/platform-recovery.yml)
uses read-only local SecretSpec preflight, then dispatches an actual bounded
[bootstrap Job](../../../ansible/roles/platform/templates/recovery-job.yaml.j2).
`task platform:recover app=<comma-separated-registered-scope>
operation=<recovery-id>` is restricted to a fresh cluster or an exact retry of its
API journal. It refuses existing GitOps Applications, registered controllers,
and surviving consumer Pods. Every selected application needs a shipped source
chart; future registry entries are refused before cluster mutation.

An already held competing shared maintenance Lease refuses before platform
writes. Only coordination/executor namespaces and a suspended Job may precede
single-winner acquisition of `selfhosted/shared-data-operation`. Its actual Job
UID owns the Lease and durable cold journal before executor grants, existing ESO
credential delivery, or unsuspension. The local process never runs chart or
recovery writes after dispatch. The executor runs in `platform-system`, outside
the ordinary data actor's Pod-creation namespace. Its temporary chart privileges
cover Kubernetes platform APIs, with no Talos administrator credential or API.

The worker proves its projected token's actual Pod UID through native
SelfSubjectReview. Before taking Pod ownership, its authenticated node-name and
node-UID claims must be nonempty and unambiguous, match the actual Pod assignment,
and equal the current Ready Node identity; missing or mismatched claims refuse.
The actor records that verified identity for later fencing. It also checks the
Job/Pod/ServiceAccount chain, immutable image
reference, actual runtime-code checksum, and shared Lease/journal at mutation
boundaries. The image's build revision is distinct from the requested GitOps
revision: a pin-only commit can use it only when runtime code matches exactly.
A size-bounded immutable ConfigMap carries checksum-bound public YAML assets
from `git archive <revision>`, excluding ignored files, credentials, and executable
paths. Extraction permits regular files only in the intended configuration paths.
The image build also uses a committed public whitelist, pinned native Helm, and
build provenance checked against its actual installed files.

This dispatch requires functioning node scheduling, base CNI, DNS, and registry
access before platform bootstrap; it does not replace Talos creation or repair
those prerequisites. Failed or interrupted workers leave ownership held.
`fence=true` permits retry of expired same-operation execution only after exact
old Job/Pod deletion, Ready-node and original node-UID checks, and confirmed
absence. A terminal old worker also needs those barriers. Lease expiry alone
never proves fencing; an unavailable/replaced node or unknown old identity
requires external repair. The watchdog refuses unfinished cold/non-Pod ownership
and cannot resume it as backup. No force deletion or automatic unsafe takeover
is provided. Success releases the exact Lease after recording held infrastructure;
only exact terminal executor grants/assets are cleaned, while the API journal
and data bindings remain.

The [recovery tasks](../../../ansible/roles/platform/tasks/recovery.yml) render
native pinned charts and create every consumer controller at zero replicas from
its first apply, including chart-owned auxiliary services. All rendered CronJobs
start suspended. Root and child Applications start without automatic sync and
with reconciliation skipped. The ApplicationSet starts with an empty list
generator, a nonautomatic child template, and create-only policy. No ordinary
root handoff runs. Retry binds source revision, registry, scope, recovery token,
and immutable resource identities in an API ConfigMap; compare-and-swap journal
updates refuse a raced or replaced identity. A deleted bound PVC, Secret, or
controller is refused before retry writes; only never-bound intent is creatable.

Only recovery infrastructure starts: PostgreSQL, Redis, Restic, and the shared
data tooling/storage. Tuppr CRDs are present, its controller starts at zero, and
its chart disables the unused Talos administrator ServiceAccount and unavailable
webhook. Upgrade custom resources are never applied. Recovery selects core,
RBAC, ExternalSecret, and CRD resources explicitly; ingress routes and DNS
endpoints remain absent until later admission. An unsupported rendered kind or
Helm hook fails closed in recovery resources. Foundational Helm hooks are disabled
in cold mode; the verified worker creates and retains the journal-bound Argo
cache credential directly. Its HTTPRoute stays disabled. This path does not
require optional ingress or DNS CRDs.

Set `HOME_OPS_COLD_RESTORE=true` for the existing database-aware restore command
with the exact same selected scope. The operations image must contain the new
cold recovery tasks and be published and digest-pinned first; the Job command
refuses an older image before running its playbook. Restoration requires a
manifest-bearing snapshot, retained application encryption keys, namespace-local
credentials, zero original writers, and matching bootstrap resource UIDs.
Selected PostgreSQL roles and intended Redis ACLs are provisioned or verified
under the same maintenance Lease before destructive recovery. Sparky's owner and
runtime roles retain their registry separation. Successful native restoration and
validation produce a journal-bound receipt. Restore recomputes the original
registry/revision digest before provisioning or replacement, even if the current
registry ConfigMap matches a changed registry. The receipt also binds actual
restore-image runtime code and build provenance separately from source revision. Generic resume restores the recorded
zero replicas and held policies; it does not admit applications.

**Activation blocker:** an executable runtime admission finalizer has not shipped.
The [admission interface](../../../ansible/roles/platform/tasks/recovery_admission.yml)
only validates completed restore evidence and returns the exact scope, revision,
recovery token, registry/source digest, verified restore tooling, snapshot/manifest
hashes, and whether global root admission is
eligible. It never enables reconciliation. Partial restoration cannot authorize
global root: every native and file consumer must have validated coverage first.
The future finalizer must recheck live identities and holds, apply exact source
settings only for validated applications, keep every unselected application held,
refence on failure, and resume root last. Only successful global finalization may
persist `phase: admitted` with its full bound `admission` record. Ordinary
`platform:create` refuses every unfinished or partial cold journal; a completed
global-admission journal permits the normal bootstrap path again. Do not edit the
journal to bypass this boundary or treat receipt generation as operational DR
completion.

Native Helm and synthetic API tests verify source identities, first-apply holds,
retry/failure sequencing, and the admission guard. They do not prove live Talos,
NAS, Bitwarden, or application acceptance after disaster recovery.

## Native adapters and recovery boundaries

The [data adapter](../../../ansible/roles/shared_data/files/data_tools.py)
creates restricted PostgreSQL application roles and database grants, produces
custom-format dumps, and restores only selected databases. Credentials are
read from mounted files. Application connection budgets leave administrator
capacity below the server ceiling. Provisioning reruns do not silently rotate
passwords. Cluster-wide application privileges are rejected.

Redis users have separate passwords, logical databases, and Pub/Sub channel
prefixes. Logical databases share one trust and failure boundary: Redis ACLs
do not restrict which logical database a user can select. The adapter blocks
global administrative and destructive commands; real application queue,
cache, and Pub/Sub acceptance remains a rollout requirement. A selected Redis
database can be recovered from a temporary isolated source while preserving
absolute key expirations and other allocations.

The [capture helper](../../../ansible/roles/shared_data/files/capture.py)
pre-copies selected files while writers remain online, then finalizes a
stopped-writer generation with content checksums and durable rename publication.
The normal pause budget begins before producers are paused, includes draining,
and is never restarted after writers stop. Expiry aborts capture; safely
finishing active application work can require a longer pause. The
[upload helper](../../../ansible/roles/shared_data/files/upload.py)
creates pending Restic snapshots and promotes only a successful, verified
generation. Exit code 3 remains pending. Raw PostgreSQL files, Redis persistence,
and staging files are excluded. Deployment wiring must mount the exact
published generation in a newly created upload Pod at the canonical paths.
Uploader Jobs start suspended with their immutable node assignment fixed to the
coordinator's authenticated original node. The exact Job UID and original node
binding reach the API journal and external claim before guarded unsuspension.
Uploaders remain tokenless. Successful claim cleanup still requires the exact
terminal Job/Pods, original Ready Node UID, and verified receipt; unbound or
ambiguous children retain their claim and generation for inspected recovery.

Provisioning new credentials needs an authorized Bitwarden write path.
The ESO/SecretSpec machine account normally has read-only access. If an operator
temporarily grants it write access for provisioning, restore read-only access
after delivery and authentication are verified. Keep values in Bitwarden and
deliver namespace-local Secrets through ESO.

## Operator commands and monitoring

`task data:backup`, `data:provision app=<name>`, `data:restore app=<name>`,
`data:restore-all`, `data:cleanup`, and `data:watchdog` preview their scope without contacting
the cluster. Set `confirm=true` only after reviewing the plan. Confirmed
commands submit bounded Jobs using the same role as scheduled operations.
The captured registry must still match the live registry before data Jobs
acquire maintenance ownership; delayed Jobs cannot apply obsolete mappings.

Native backup and provisioning accept only entries in `registry.consumers`,
including existing SQLite consumers before onboarding. File-only entries in
`registry.file_consumers`, whether selected alone or alongside native consumers,
are rejected before preview, Job submission, or maintenance coordination. Restore
and cleanup continue to accept combined native and file scopes. Direct backup
and provisioning task entry points enforce the same guard before cluster access.

`data:cleanup confirm=true` separately forgets unpromoted pending snapshots
older than seven days. It holds reconciliation and schedules, verifies upload
actors are finished, and leaves application writers online. Canonical snapshots,
including ambiguous snapshots carrying both tags, are never eligible. Normal
repository retention applies across all host/path/tag groups, including workstation
snapshots, and explicitly keeps every `appdata-pending` snapshot for this separate
cleanup. Repository pruning later reclaims unreferenced data.

Restore stages and validates the selected snapshot before replacing data.
The API journal binds snapshot identity, exact manifest bytes, and selected
scope. PostgreSQL-era recovery requires database manifests, compatible images,
and retained encryption keys. Historical manifest-less snapshots are accepted
only for consumers still using their file or SQLite backend. A selected Redis
allocation is recovered through an authenticated, isolated temporary Redis
source, leaving other allocations unchanged. Failures after destructive work
remain held for inspection.

Gatus operation health and backup freshness have separate external endpoints.
The API-only watchdog reports stale ownership and failed coordinator/upload
Jobs. Backup freshness uses the capture time of the last verified full-scope
upload, rather than upload completion or provisioning time; delayed retries
cannot overwrite a newer capture record. Its heartbeat credential is mounted
only in the watchdog, without database credentials or NFS. Endpoints remain
disabled until rollout acceptance. These checks cannot provide an external
alert during a complete single-node or monitoring outage.

## Image and verification

The [image workflow](../../../.github/workflows/data-tools.yml) builds on PRs
and publishes commit-tagged images from master. Consumers must use the
published digest. The image contains PostgreSQL-major-matched clients, Redis
tools, Restic, and the role-owned adapters. It carries no operator secrets.

Unit and synthetic Kubernetes API scenarios verify input guards, original
state, concurrency and interruption behavior. Disposable PostgreSQL and Redis
tests verify role restrictions, custom dump recovery, types and sequences,
ACLs, and selected database recovery. Native Restic tests use a disposable
local repository. These checks supplement fresh-install, migration rehearsal,
single-app restore, cold-recovery, and failure acceptance in the rollout plan.

## Sources

- [Role defaults and entry point](../../../ansible/roles/shared_data)
- [Operations playbook](../../../ansible/playbooks/shared-data.yml)
- [Image build](../../../containers/data-tools/Dockerfile)
- [Maintenance integration scenarios](../../../tests/integration/test_data_maintenance.py)
- [Native database scenarios](../../../tests/integration/test_data_native.py)
- [Native Restic scenario](../../../tests/integration/test_data_restic.py)

## Related pages

- [Backup and recovery](../architecture/backup-recovery.md)
- [Restic procedure](restic-backup-restore.md)
- [Secrets maintenance](secrets-maintenance.md)
- [GitOps delivery](../architecture/gitops-delivery.md)
