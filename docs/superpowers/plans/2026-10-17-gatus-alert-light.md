# Gatus Alert Light Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `light.office_office_mood_light` steady red for confirmed Gatus alerts and restore its original state after the final recovery.

**Architecture:** Gatus's native Home Assistant alert provider feeds one queued Home Assistant worker. Persistent helpers retain open warnings and the original light state; a 30-second check of Gatus history repairs missed events. Repository-owned packages and templates preserve existing UI-managed configuration and Matter storage.

**Tech Stack:** Existing Gatus v5.37.0, Home Assistant 2026.10.1, native Home Assistant packages/scripts/helpers/REST commands, Jinja, Kubernetes/Argo CD, Bitwarden/ESO, pytest.

**Spec:** [Approved design](../specs/2026-10-17-gatus-alert-light-design.md).

## Global Constraints

- Target `light.office_office_mood_light`; warning RGB `[255, 0, 0]`, brightness 50%.
- Five consecutive failed checks trigger; two successful checks resolve. Preserve Telegram and require identical provider policies.
- One queued worker handles both events and reconciliation. Do not overwrite the first snapshot on duplicate or overlapping alerts.
- Persist helpers without `initial`. Keep snapshots at or below the input-text limit of 255 characters.
- Reconcile at startup, every 30 seconds, and when the bulb becomes available.
- Use `http://gatus.platform-system.svc/api/v1/endpoints/statuses` and `http://homeassistant.home-automation.svc:8123` internally.
- Keep credentials in Bitwarden/ESO, mounts read-only and HA-only, and existing PVC identities unchanged. Add no production service or custom integration.
- Stay on `codex-gatus-alert-light`; PR-only delivery, current-head CI, exact-head merge. Run `task fmt` and `task check` before commits.
- Existing design validation hit `test_command_failure_terminates_child_processes[TimeoutError]` on an empty PID file; its focused rerun passed. Report recurrence separately; do not silently waive a failing gate.

## Review Focus

1. A delayed resolved event must not clear a newer five-failure incident: Task 2 tests the event against fresh history before allowing restoration.
2. An unavailable bulb must neither destroy the snapshot nor falsely complete restoration: Task 2 exercises deferred snapshot and restore retries.
3. A truncated/restarted Gatus history must not invent recovery: Task 1 covers insufficient, missing, stale, and malformed history while retaining prior state.
4. A renamed, removed, or colliding endpoint must not strand or misassign a warning: Tasks 2/3 enforce catalog coverage; Task 5 explicitly retires acceptance helpers only after recovery.
5. A restart while the bulb is red must preserve the original colored/off state: Task 2 runs the real HA script engine across a clean restart; Task 5 repeats physical acceptance.

## File Map

| File | Responsibility |
| --- | --- |
| `apps/home-automation/homeassistant/manifests/homeassistant-gatus-alert-light.configmap.yaml` | Package YAML and pure Jinja macros, in separate ConfigMap keys |
| `apps/home-automation/homeassistant/manifests/homeassistant-config.configmap.yaml` | Enable package-directory loading; preserve existing includes |
| `apps/home-automation/homeassistant/values.yaml` | Mount package and macro only into HA, through a ConfigMap volume |
| `apps/platform-system/gatus/values.yaml` | Add native provider and per-endpoint alert selection, sharing Telegram thresholds |
| `apps/platform-system/gatus/manifests/gatus-credentials.externalsecret.yaml` | Deliver the dedicated HA token alongside existing Telegram fields |
| `tests/unit/test_homeassistant_alert_light.py` | Execute real production macros against literal input/output cases |
| `tests/config/kubernetes/test_homeassistant_alert_light.py` | Package/catalog/provider/security and rendered mount/PVC contracts |
| `tests/support/homeassistant_alert_light.py` | Run the real HA script engine in an isolated temporary config with device/network boundary doubles |
| `docs/wiki/apps/home-automation/homeassistant.md`, `docs/wiki/apps/platform-system/gatus.md`, `docs/wiki/architecture/uptime.md` | Operation, alert semantics, and limitations |
| `docs/wiki/architecture/backup-recovery.md`, `docs/wiki/operations/restic-backup-restore.md`, `docs/wiki/sources.md`, `docs/wiki/log.md` | Persistent warning-state recovery, sources, and ingest |

Temporary acceptance resources in Task 4 belong to Gatus's existing app and are removed in Task 5. They are not a new permanent application.

## Task 1: Implement and test pure state/history templates

**Files:** Create the new ConfigMap with `gatus_alert_light.jinja`; create the unit test file.

**Interfaces:**
- `reduce_history(results, previous_active, now_ts, failure_limit, success_limit)` returns JSON with `valid: bool`, `active: bool`, and `transition: "triggered" | "resolved" | ""`.
- `normalize_event(payload, endpoint_names)` returns JSON with `valid`, `endpoint`, and `status`; consume nested `payload.event_data` and exact `group/name` identifiers.
- `snapshot_light(state, attributes)` returns JSON with `valid` and `snapshot`. A valid snapshot contains `state`, and for an on light, brightness plus exactly its active color mode's restoration fields.

- [ ] Write parameterized tests with hand-derived expectations: four failures stay clear; five activate; one success retains; two resolve; overlapping failure/recovery runs use the last decisive transition. Use different prior flags to prove insufficient history preserves them.
- [ ] Test empty/non-list history, missing or non-boolean success values, invalid timestamps, duplicate/out-of-order timestamps, latest result older than 180 seconds, and more than 30 seconds in the future. Older retained records are allowed when the latest record is fresh.
- [ ] Test flat/malformed/unknown-endpoint events are rejected and nested `event_data` is recognized. Test snapshot round trips for on/77/2202K, HS blue, XY color, and off; unavailable/unknown states and over-capacity snapshots are rejected.
- [ ] Pin these named assertions in the new unit tests (the test fixture renders the production macro and JSON-decodes its result):

```python
@pytest.mark.parametrize("results,previous,active", [
    ([False] * 4, False, False),
    ([False] * 5, False, True),
    ([False] * 5 + [True], False, True),
    ([False] * 5 + [True, True], False, False),
    ([False, True, False], True, True),
])
def test_history_hysteresis(reduce_history, results, previous, active):
    assert reduce_history(results, previous)["active"] is active
```

The `reduce_history` test fixture wraps those literal successes with valid ordered fixture timestamps; it does not compute the expected active state. Also name the independent invalid-data and snapshot cases `test_invalid_history_preserves_open_warning`, `test_nested_event_identity`, and `test_snapshot_restoration_fields`.

- [ ] Run `PATH="$PWD/.venv/bin:$PATH" task test -- tests/unit/test_homeassistant_alert_light.py`; observe failure for missing production templates.
- [ ] Implement macros in the ConfigMap. Fold valid history chronologically with consecutive counters, resetting the opposite counter on each result. With no decisive transition, retain the prior flag. Serialize compact JSON and avoid Home Assistant globals in macro logic except explicit timestamp/JSON filters.
- [ ] Run the unit tests to green, then `task fmt`, `task check`, and `git diff --check` under the project venv PATH. Commit only this tested unit and its tests.

## Task 2: Add the native Home Assistant worker, persistence, and package mounts

**Files:** Extend the new ConfigMap; modify the existing HA config and values; create the configuration tests and isolated HA-engine runner.

**Consumes:** Task 1 macros. **Produces:**
- `script.gatus_alert_light_worker(kind="event" | "reconcile", payload={})`, queued, maximum 100 queued runs.
- `input_text.gatus_alert_light_snapshot`, max 255, no `initial`.
- One `input_boolean.gatus_alert_<slug>` per monitored endpoint. Mapping lives in `script.gatus_alert_light_worker.variables.endpoints`, keyed by exact display identifier. Assert unique helper IDs and complete source-catalog coverage.
- `rest_command.gatus_alert_light_status`, GET the fixed internal Gatus URL, timeout 5 seconds. Its native result is `{status, content, headers}`; JSON content is already decoded by the installed HA version.
- `automation.gatus_alert_light_dispatch`: Gatus event, HA start, 30-second timer, and bulb availability triggers dispatch into the same worker. Use parallel dispatch with the queued worker as the sole state-changing owner.

- [ ] Add failing configuration/rendered tests for missing package loading, writable/shared mounts, changed PVC names, reset-on-start helpers, non-queued processing, wrong target, missing endpoint helpers, and wrong nested event handling. Execute macro cases rather than asserting source spelling.
- [ ] Add an isolated native-engine runner. Load actual package/macros into a new temporary HA configuration using the installed HA libraries. Stub only the Gatus HTTP boundary and physical light service boundary; use real scripts, helpers, events, and restoration storage. Never load production auth/storage or start another Matter controller.
- [ ] Add runner cases named `one_alert`, `duplicate`, `overlap`, `stale_resolution`, `missed_delivery`, `invalid_event`, `bad_api`, `initially_off`, `colored_snapshot`, `deferred_snapshot`, `deferred_restore`, and `restart`. Assert initial red, duplicate snapshot preservation, two overlapping alerts, stale resolved event versus fresh failure history, missed trigger/recovery repair, rejected malformed events, API failure/staleness, initially-off/color-mode restoration, light unavailable before snapshot, light unavailable during restore, and clean restart while red.
- [ ] Run the focused configuration tests RED. Execute the initial engine scenarios and confirm the missing worker fails.
- [ ] Add package loading under `homeassistant.packages: !include_dir_named packages`, preserving all existing UI includes. Mount the package at `/config/packages/gatus_alert_light.yaml` and macros at `/config/custom_templates/gatus_alert_light.jinja`, HA-only/read-only. Existing PVCs must remain `homeassistant` and `homeassistant-matter`.
- [ ] Implement worker validation and reduction. Wait until helper states are initialized. Reject invalid event payloads without touching state; reconciliation runs fetch and validate source history. Unknown/missing/invalid endpoint data retains the prior flag. Valid history is authoritative; an authenticated triggered event can activate its known endpoint when history is insufficient, while resolved events require fresh recovery evidence.
- [ ] Implement snapshot-before-red ordering. Only save when no valid snapshot exists and the bulb is available. Apply red with `light.turn_on`, RGB `[255,0,0]`, brightness 50%. If an active warning has no snapshot and the bulb is already red, do not assume red was its original state; keep state for operator recovery.
- [ ] Restore only when every open warning has fresh evidence allowing it to clear. Keep the final open flag(s) and snapshot until restoration succeeds, then clear the snapshot and flags. This leaves recovery evidence available for retries without another helper. For partial recovery while another warning remains, clear only the recovered endpoint's flag.
- [ ] Restore using `light.turn_off` for an originally-off light or `light.turn_on` with saved brightness and only the saved mode's color fields. Verify on/off, brightness within one level, Kelvin within 25K, circular hue within 2 degrees/saturation within 2 points, or XY components within 0.005 before clearing state (only the saved mode applies). Unavailable/API failure must retain recovery state for the next run. Do not continuously resend unchanged red/restored commands.
- [ ] Run native HA configuration validation with `python -m homeassistant --script check_config --config <fresh-validation-directory>` (exit 0 required), then run `python <staged-runner> <package.yaml> <macro.jinja>` inside the existing HA image. The runner owns a fresh `TemporaryDirectory` and prints each named scenario plus a final all-passed result; it must exit nonzero on an assertion. Keep all files under a fresh `/tmp` directory, no production configuration reload yet. Run focused tests GREEN, `task fmt`, `task check`, `git diff --check`, and commit.

## Task 3: Wire Gatus events, prepare credentials, and document operations

**Files:** Modify Gatus values/ExternalSecret, extend configuration tests, and update the wiki files listed above.

**Consumes:** Queued worker and endpoint mapping from Task 2. **Produces:**
- Gatus `alerting.homeassistant` with internal HA URL and token `$HOMEASSISTANT_GATUS_TOKEN`.
- `HOMEASSISTANT_GATUS_TOKEN` delivered from Bitwarden key `homeassistant_gatus_token` through existing `gatus-credentials`.
- Both providers share failure 5, success 2, send-on-resolved true; every permanent target retains Telegram and also selects `homeassistant`.

- [ ] Write failing contracts for a missing HA provider/endpoint selection, divergent thresholds, disabled recovery notifications, removed Telegram selection on permanent targets (the temporary `acceptance` group is HA-only), literal credentials, and incorrect secret references. Pin source assumptions: no maintenance suppression or per-endpoint threshold overrides unless reconciliation supports them.
- [ ] Run focused tests RED, implement provider and external-secret mapping, then run GREEN. Do not enable a missing-secret deployment.
- [ ] Request operator credential setup only after the complete configuration is reviewable: create a dedicated named HA access token and store it directly in the existing Bitwarden `home-ops` project as `homeassistant_gatus_token`. Use an administrator account: the installed HA event endpoint requires it. A dedicated account allows independent revocation; the token inherits broad administrator permissions. Never request the value in chat or broaden the existing read-only BWS machine account to obtain write access.
- [ ] Before merge, verify read delivery using a uniquely named temporary ExternalSecret/Secret in `platform-system`, the existing store, and only the new key. Check readiness/key presence without printing values; remove that diagnostic resource afterward. The permanent target Secret receives the key when the new spec syncs after merge.
- [ ] Document configuration ownership, persistent snapshot/open-warning helpers, manual light changes during an active alert, restart/restore ordering, insufficient-history limits, token rotation/revocation, target retirement, and rollback. Update sources/log; do not repeat October's semantic review.
- [ ] Run `task fmt`, focused Kubernetes/wiki tests, `task check`, and `git diff --check`. Request one fresh-context whole-branch review; fix substantive findings with regression tests. Commit tested changes.

## Task 4: Deliver and exercise the real alert path without disrupting a service

**Temporary files:** Add app-owned fixture ConfigMap, Deployment, and Service under `apps/platform-system/gatus/manifests/gatus-alert-light-acceptance.*.yaml`; add two temporary Gatus endpoints and matching helper mappings.

**Fixture contract:** One unprivileged HTTP process serves `/a` and `/b`, returning 200 or 503 according to files in an `emptyDir`. No ingress, credentials, host networking, or PVC. Test targets use group `acceptance`, names `alert-light-a`/`alert-light-b`, five-second intervals, the same 5/2 thresholds, and only the HA provider so synthetic checks do not send Telegram messages.

- [ ] Add focused coverage for temporary endpoint/helper identity, fixture-only failure control, and absence of public exposure/PVCs. Run RED, add the fixture and targets, run GREEN. The executor may use a current official Python image for this temporary fixture, pinned and checked against the repository's update conventions.
- [ ] Run `task fmt`, `task check`, and `git diff --check`. Push/open a PR including the approved spec/plan and wiki changes; attach it to the chat. Credential preflight must be successful before merge.
- [ ] Wait for Format, Lint, Tests, and Quality Gate on the fresh current head. Squash-merge against that exact SHA. Independently verify GitHub merge state and `origin/master`; run the merged-master gate.
- [ ] Sync HA and Gatus, verify both applications at the merged revision, both HA containers Ready, unchanged PVC bindings, successful secret delivery, and no recurring errors. Confirm normal Telegram configuration still loaded without dumping its credentials.
- [ ] Record the bulb's initial available state and take a fresh backup. Through `kubectl exec` against only the acceptance fixture, change `/a` to 503. Verify no warning after four checks, red after five. Fail `/b`, recover `/a`, and prove the warning remains; recover `/b` and prove full restoration after two successes.
- [ ] Repeat with an initially-off bulb. With an active synthetic alert, restart HA/recreate its pod and verify helper/snapshot persistence, Thread route recovery, red warning, then restoration without repairing. Avoid claiming hard-crash atomicity.
- [ ] Use the isolated engine runner to exercise dropped resolved events and delayed messages deterministically; combine this with the real-provider/real-bulb checks above rather than changing production network policy to drop traffic.
- [ ] Confirm Apple Home remains functional and receives the restored state. Restore the user's initial light state after all tests. Capture a screenshot with no credentials or pairing codes.

## Task 5: Remove acceptance resources and close delivery

**Files:** Remove only Task 4's fixture manifests, two Gatus test endpoints, and two test-helper mappings; update temporary-only tests accordingly.

- [ ] Require both synthetic warnings resolved, test helpers off, and snapshot empty before retiring their source entries. If not, finish recovery first; never clear a warning merely because a row disappeared.
- [ ] Remove fixture resources/targets/helpers. Keep the final catalog contract derived from the permanent Gatus targets. Run focused tests, `task fmt`, `task check`, `git diff --check`, and fresh review of the cleanup diff.
- [ ] Deliver cleanup through a follow-up PR with fresh exact-head CI and protected merge; attach it. Verify GitOps prunes the temporary Deployment/Service/ConfigMap and that the permanent catalogs, warning automation, Telegram, and bulb all remain healthy.
- [ ] Verify a fresh Restic snapshot contains both HA and Matter claim paths; `task restic:restore app=homeassistant` must select both without changing anything. Preserve a compatible state backup before changing automation formats later.
- [ ] Restore any temporary operational overrides, remove diagnostic/preflight Jobs/Secrets, and clean only task-owned branches/worktrees. Do not purge HA history or unrelated storage.
- [ ] Final report: merged PRs, exact-head gates, physical red/restore and overlap results, restart and backup evidence, initial state restored, and any remaining limitations. Never report completion with an active test warning, missing credential, paused reconciliation, or temporary fixture left behind.

## Execution recommendation

Use native inline execution (`superpowers:executing-plans`) with one fresh whole-branch review. These tasks share a small package/template interface, and a single context avoids repeated rediscovery of HA state semantics. The physical acceptance is deliberately split from final cleanup so it uses the real provider and worker without taking down a production service or adding test-only hooks to the permanent automation.
