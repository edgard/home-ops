# Paperless shutdown enrollment

Purpose: move an existing Paperless Pod to the registered shutdown settings
without interrupting accepted work.
Status: current. Reviewed against: `baf431037c87ed50220bb3fee4cb5e96c0568184`.

## Prerequisites

Publish and digest-pin an operations image containing the enrollment role, and
apply its scoped RBAC before beginning. Keep the Paperless values change in a
separate PR. The ordinary backup protocol checks the actual Pod's shutdown
settings; changing a Deployment template does not change an existing Pod.

Use a nonsecret local JSON settings file with `shared_data_operator_step`,
`shared_data_operation_kind: migration`, a unique `shared_data_operation_id`,
`shared_data_apps: [paperless]`, and the exact published `shared_data_image`.
The [defaults](../../../ansible/roles/shared_data/defaults/main.yml) define
session lifetime and drain budgets. Choose a Lease long enough for the held
merge and renew it explicitly; the actor has a bounded lifetime independent
of the caller. Do not put credentials in this file.

`task data:operator settings=/absolute/path/session.json` previews the step,
actor identity, image and source revisions without contacting Kubernetes.
`confirm=true` explicitly executes it; a confirmation inside the file does not
replace the Task argument. Run steps serially from the same session.

## Held transition

1. Run `create`, then retain the returned name and UID in
   `shared_data_holder_pod_name` and `shared_data_holder_pod_uid`. Keep the exact
   operation ID and image. The standalone actor has temporary storage, no NFS
   mount or database credentials, and cannot be replaced by a completed Job.
2. Run `prepare` to record original identities and settings and hold root,
   ApplicationSet, affected Applications, schedules and node upgrades.
3. Set `shared_data_source_revision` to the exact registered desired commit and
   run `enroll`. Clean local Git sources and native Helm rendering must match
   that source. The role records pause intent, stops GPT, withdraws registered
   Service endpoints, pauses inbox/beat producers and cancels Celery consumption.
   It keeps the original web process and its probe alive until scheduled,
   reserved and active work and accepted connections drain. The private Redis
   remains unchanged. Only after idle are main and GPT held at zero.
4. Merge only the reviewed shutdown settings PR while the hold remains active.
   Use `renew` before Lease expiry; there is no asynchronous heartbeat.
5. Fetch the merged source, set `shared_data_target_revision`, and run `apply`.
   The role verifies the registered desired revision and independently renders
   both sources. Only the approved shutdown-related template fields may change;
   all other rendered resources must match. The patch atomically tests main's
   UID, resource version and zero replicas.
6. Run `resume`. The actual new main Pod must be Ready and prove the protected
   image, grace and native settings before route, GPT and schedules resume.
   Child reconciliation follows, with root last.

## Failure handling

An expiry while draining leaves the original Pod alive and reconciliation held.
`abort` can restore native producer/consumer and route state before the source
change, only while the desired source still matches the original render. After
merging the new template, abort refuses to unfence an old Pod: continue through
`apply` and `resume`. Neither path rolls the template back.

Unexpected identity, broker, template or desired-source changes retain the hold
for inspection. An expired/dead actor requires separately inspected administrative
recovery; changing the actor UID is not a takeover mechanism. Interrupted
backup-kind enrollment can restore only proven native pause/route state while
keeping controllers and root held for source-aware recovery.

Service withdrawal and socket inspection provide route draining, not
NetworkPolicy isolation. Direct Pod clients and controller/dataplane convergence
require live acceptance. Disposable native application and synthetic API tests
support the procedure; they do not establish production rollout completion.

## Sources

- [Operator sessions](../../../ansible/roles/shared_data/tasks/operator.yml)
- [Enrollment coordinator](../../../ansible/roles/shared_data/tasks/enrollment.yml)
- [Git and Helm source verification](../../../ansible/roles/shared_data/files/enrollment_source.py)
- [Protected application](../../../ansible/roles/shared_data/tasks/enrollment_apply.yml)
- [Source-aware resumption](../../../ansible/roles/shared_data/tasks/enrollment_resume.yml)
- [Portable integration scenarios](../../../tests/integration/enrollment)
- [Task entry point](../../../Taskfile.yaml)

## Related pages

- [Shared application data operations](shared-data.md)
- [Paperless](../apps/selfhosted/paperless.md)
- [GitOps delivery](../architecture/gitops-delivery.md)
