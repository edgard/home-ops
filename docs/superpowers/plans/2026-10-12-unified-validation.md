# Unified validation simplification implementation plan

> For implementers: execute the tasks below in order using the executing-plans workflow. This document authorizes planning only; implementation is a separate step.

**Goal:** Replace the fragmented Ansible/policy testing architecture with native validators and one pytest suite, reducing hardcoded expectations and custom plumbing while preserving operational safeguards.

**Architecture:** Production orchestration remains in Ansible playbooks and roles. Native tools own syntax, schemas, deprecations, and language-specific validation. pytest owns repository configuration assertions, adapter units, and isolated execution tests, including every existing Ansible test suite. Conftest, Rego, task-structure reconstruction, and nested test runners are retired.

**Tech stack:** Existing Ansible, native CLIs, PyYAML, JSON5, jsonschema, and Python TOML support; add pinned pytest and python-hcl2. Use existing dependency/Renovate conventions for those additions.

**Spec:** The agreed scope, interfaces, migration tasks, and acceptance criteria are recorded together in this document. This replaces the earlier Conftest-focused plan.

## Constraints and design decisions

- Preserve operator Task commands, argument/default behavior, credential ownership/scopes, and runtime assertions. Do not change deployments, rotate credentials, or sync Argo CD as part of this refactor.
- Keep operator orchestration and focused runtime adapters in Ansible. Add no top-level scripts workflow, Molecule, custom policy engine, rule registry, generic assertion DSL, or permanent mutation-testing framework.
- Retain native formatting, yamllint, ansible-lint, actionlint, kubeconform, Pluto, Git artifact checks, wiki validation, and OpenTofu validation. pytest does not reimplement their semantics.
- Replace configuration inventories with parsed source objects. Preserve types instead of converting booleans/numbers to strings. Parse HCL with python-hcl2, not regular expressions, and verify Terraform sensitivity with OpenTofu.
- Discover application directories and documents from current sources. Required missing/malformed inputs and unexpectedly empty discovery fail. Removing a complete application remains a reviewable GitOps change rather than a fixed-list violation.
- Preserve deliberate security exceptions with their reasons. Replace duplicated operational versions, IPs, ports, and identifiers with relationships to owning configuration. Fixed safety bounds and documented compatibility limits remain legitimate expectations.
- Tests use temporary HOME/config/output paths and synthetic credentials. Sanitize inherited credential variables. Kubernetes fixtures point only to a local API; fake CLIs never fall through to real executables.
- New behavior checks follow a fail-first cycle. Do not remove an old check before its replacement demonstrates the protected behavior, or before native-tool coverage/redundancy is established.
- Preserve positive and negative regression cases, not just checks against today's valid checkout. Account for existing cases without preserving implementation-specific test counts, source spellings, or error prose. Do not broaden exceptions or tighten unrelated configuration semantics during this migration.
- Required tests may not silently skip or xfail because discovery is empty, parsing failed, or a CLI is absent. Configure pytest's empty-parameter behavior to fail and assert expected discovered/rendered inputs independently.
- Use a feature branch and PR. Run task fmt and task lint before each implementation commit or PR update. No direct master commits.

## Final structure and interfaces

| Location or interface | Responsibility |
| --- | --- |
| tests/config/repository/ | SecretSpec ownership/scopes, Task interfaces, Terraform/Talos compatibility, protected artifacts |
| tests/config/kubernetes/ | Application metadata/values, raw/rendered resources, cross-file relationships, route coverage |
| tests/unit/ | Focused runtime parser/filter/schema/provider units and small reusable check helpers |
| tests/integration/ | Real role/Task execution, command construction, check mode, cleanup, rollback, redaction, and validation pipeline behavior |
| tests/fixtures/ | Small role-invocation playbooks, synthetic resource data, fake CLIs, and the existing local API fixture |
| tests/conftest.py | Thin shared pytest fixtures; this is pytest's conventional fixture filename, not the retired Conftest CLI |
| tests/support/ | Focused source loading, subprocess, and API helpers; ordinary functions, no configurable test framework |

- `task test`: `.venv/bin/python -m pytest tests`; all repository-owned configuration, unit, and integration tests. No native lint repetition except the Kubernetes rendering/schema/deprecation pipeline required by its tests.
- `task lint:repository`: pytest against `tests/config/repository`.
- `task lint:ansible`: production-profile ansible-lint against `ansible` and retained fixture playbooks in `tests/fixtures`, followed by pytest against `tests/unit` and `tests/integration`.
- `task lint:kubernetes`: pytest against `tests/config/kubernetes`; a session fixture invokes the Ansible Kubernetes pipeline once and shares its rendered output.
- `task lint:ansible:static`: the same ansible-lint invocation only, for the full local aggregate.
- `task lint`: formatting check, static YAML lint, workflow lint, wiki validation, Ansible static lint, backendless OpenTofu validation, then `task test`. Do not also run the focused pytest commands in this aggregate.
- Small fixture playbooks invoke whole roles or existing role entry points; they never discover tests, invoke pytest, or extract selected tasks from production YAML.
- Add `kubernetes_validation_output_dir` as a required caller-owned workspace input to the internal validation playbook. The pytest fixture creates/removes it and obtains rendered YAML and exported schemas. Ansible initializes only its workspace contents and retains chart rendering, schema export, kubeconform, and Pluto. It invokes no test/policy runner.
- The output directory must already exist, be empty, private, and not a symlink. Ansible must never remove the caller's directory. Preserve `rendered/<category>/<app>.yaml` and the exporter's existing schema layout; pytest cleanup runs after both successful and failed pipelines. Keep per-run chart caching/retries and isolated Helm config/cache/registry paths, existing release/API-version arguments, and the repository Kubernetes target.
- Source checks parse application metadata/values directly. Rendering consumes the original chart declarations plus minimal derived app identity, without the former policy inventory flags or string conversions.
- The rendering fixture first runs the same ordinary source-validation helpers used by source tests, so malformed/missing metadata cannot reach Helm regardless of pytest execution order. Shared rendering is requested only by rendered tests, never by global/autouse fixtures. Keep native Kubernetes pipeline tests in the Kubernetes subset; the Ansible subset requires no real Helm/kubeconform/Pluto installation.

## Audited coverage baseline

At `e66f8dac`, the source contains nine Python modules with 40 test methods, nine top-level YAML suites, and 208 Rego regression cases across five policy layers. These are audit observations, not permanent expected counts. Every case must receive a migration disposition in the PR checklist, including cases for adapters/runners that are being retired.

| Existing surface | Required destination or demonstrated replacement |
| --- | --- |
| Python: test_crd_schemas, test_secrets, test_secret_delivery, test_talos_generation | Focused parser/schema/provider units plus real launcher, Talos, SecretSpec, and secret-delivery integration scenarios |
| Python: test_operator_patterns, test_role_contracts | Whole-entry-point operational tests in Task 3; retire source-task selectors after their safety scenarios pass |
| Python: test_repository_inventory, test_terraform, test_renovate | Direct typed source-loading/regression checks, native OpenTofu sensitivity, real validation-boundary tests, and native regex/discovery checks |
| YAML: cluster-secrets, secret-unit, secrets-setup, native-conventions, restic-restore, talos-upgrade | pytest units/integration; fixture playbooks only invoke real entry points or export facts |
| YAML: source-inventory, uptime, wiki-contracts | Source/embedded-parser and route-coverage regression cases plus actual wiki-role execution; retire inventory-file cleanup assertions when that inventory no longer exists |
| Fixture cases: cluster-access-case, cluster-handoff-case, cluster-token-case, cluster_api | pytest parameterized scenarios and shared loopback API lifecycle, including ambiguous patches, API failures, rollback failures, root revision changes, and ApplicationSet recreation |
| Repository policy | Valid/distinct project UUIDs including allowed additional providers; Keychain/no-cache/environment delivery; exact scopes and ownership; shared Tailscale item; native Terraform wiring/sensitivity, provider compatibility, and retired-provider/workflow absence; Talos target alignment and documented support bounds; pipeline behavior and Git credential/backup protection |
| Metadata/source policy | Missing/empty files, chart/sync-wave/ignoreDifferences shape, unique generated names, supported chart majors, primary controller/service/route wiring, root/non-root/shared-media profiles, optional-section ordering, owned filename/field order with vendored exceptions, Argo CD chart route ownership, gateway DNS/Multus relationship; Karakeep browser/sandbox/port wiring, Radarr/Sonarr/Prowlarr TMPDIR/capabilities, qBittorrent VPN health/firewall wiring, Recyclarr groups/naming, Jellyfin LAN/discovery/probes, Changedetection LLM/credential wiring, and Gatus health targets |
| Kubernetes policy | Raw and rendered resources including Argo CD sources; workloads/init containers and documented image exceptions; replicas/strategy/capabilities/non-root/shared-media security; approved storage; canonical ExternalSecret store and consumer-namespace restrictions; populated Secret rejection; pinned image tags; fail-closed Istio webhooks; unsupported NFS snapshotter rejection; route/gateway/ExternalDNS conventions; retired observability resources/annotations, Istio telemetry, and cert-manager listener exposure |
| Route policy | Valid raw/rendered host sets; Gatus self-route exclusion; missing, obsolete, and duplicate HTTP targets; Jellyfin/CrossWatch health paths; no blanket exclusion of other routed applications |
| Ansible safety policy | Check-mode effects, inherited redaction and failure behavior, credential preflight/delivery, original resource identity/state, scoped stale-object cleanup and waits, bootstrap order, warmup cleanup, restore success/failure/evidence retention, and Talos private-material cleanup; a small generic YAML-content check retains the kubernetes.core convention by rejecting kubectl command/shell tasks, without reconstructing execution flow |

## Review focus

- Moved tests must not retain test-to-test imports or old ROOT/PYTHONPATH assumptions. Centralize the root/module-loader fixture, use pytest importlib discovery, and import role-owned plugins explicitly without changing the operator's Python path.
- Keep the shared safe Kubernetes YAML dialect (including an unquoted `=` chart default), safe Recyclarr `!env_var` handling, multidocument parsing, nullable/int-or-string/composition semantics, property names that collide with schema keywords, strict unknown-field behavior, and conflicting-schema rejection.
- Preserve success and each distinct failure boundary for token rotation/handoff. Injected provider/API failures must reach their intended boundary; an unrelated early error is not proof that a rollback/redaction scenario passed.
- Restore failure can leave partially resumed workloads if the resume phase fails. Assert that behavior and retained evidence rather than incorrectly promising every failure leaves every workload paused. Do not add automatic resume/rollback that the current recovery procedure deliberately avoids.
- A fake module/CLI tests role behavior, not real Kubernetes transport or complete bootstrap. Keep real collection imports/native API cases covered, and report that pod-exec transport, live restore, and fresh-cluster acceptance remain outside this offline refactor.

## Task 1: Establish the shared suite and migration map

**Files:** Python requirements and pytest configuration; `tests/conftest.py`, `tests/support/`, and `tests/fixtures/`; existing `ansible/tests` and `policy` remain until migrated.

**Produces:** Shared source-root, temporary-workspace, sanitized-environment, fake-CLI, local-API, and Ansible execution fixtures. The Ansible runner returns the native completed-process result; fake boundaries record structured argument/API events.

- [ ] Inventory every existing Python test, YAML suite, Rego rule/test, and runner. Record its replacement, native-tool owner, or justified retirement in the PR checklist; do not maintain a new runtime contract registry.
- [ ] Carry useful valid/invalid Rego inputs into parameterized pytest regressions. Use small ordinary assertion helpers where the same semantic check needs both actual-source and synthetic-case coverage; add no policy evaluator abstraction. Missing structure and wrong types must reject rather than produce vacuous passes.
- [ ] Add pinned pytest and python-hcl2, using ordinary pytest configuration and explicit discovery under `tests`.
- [ ] Consolidate repeated subprocess/environment setup. Reuse the local Kubernetes fixture rather than introducing a general Kubernetes emulator.
- [ ] Extend that fixture only for the resource/discovery/list, scale, sync-policy patch, Job/Pod lifecycle, and failure responses used by the real collection modules. Record target identity, payload, and event order. Only pod exec uses a test-only collection module; retain a real-module load/failure-boundary check so the stub cannot hide collection/client import incompatibility. This does not claim websocket transport acceptance.
- [ ] Verify temporary-path isolation, process/server teardown after failures, synthetic-only credentials, and unexpected fake-command failure. Start API fixtures through pytest lifecycle management instead of detached playbook processes.
- [ ] Give subprocesses bounded timeouts and servers readiness checks; cleanup must not mask the original failure. Keep fixtures compatible with local macOS and Ubuntu CI, including temporary paths containing spaces and synthetic multiline/special-character values.
- [ ] Run focused pytest tests and the existing full gate before committing this independently usable foundation.

## Task 2: Move all Ansible behavior tests to pytest

**Files:** Existing `ansible/tests/unit`, top-level YAML suites, and fixture playbooks; new `tests/unit` and `tests/integration`.

**Consumes:** Task 1 fixtures. **Produces:** A single suite covering the existing adapters and all existing executable test scenarios.

- [ ] Account for all cases in the nine Python unittest modules. Migrate executable/adapter cases into focused pytest tests and defer obsolete inventory/role-policy cases to their Task 3/4 replacements. Share setup/parameterization where it removes duplication; preserve distinct normalization and execution boundary coverage.
- [ ] Migrate every YAML suite: cluster-secrets, native-conventions, restic-restore, secret-unit, secrets-setup, source-inventory, talos-upgrade, uptime, and wiki-contracts. Remove the secret-unit discovery wrapper entirely.
- [ ] Keep fixture playbooks only for real role invocation and exporting relevant Ansible facts; move fixture construction, result assertions, output capture, and cleanup ownership to pytest.
- [ ] Preserve installation/checksum handling, safe provider/material parsing, launcher credential cleanup, project/key access, fresh ESO reconciliation, committed Argo revisions, ApplicationSet ownership, token rollback, bounded Terraform cleanup, schema export, source discovery, route parsing, wiki contracts, and native Terraform sensitivity.
- [ ] Keep selected/default tool installation, corrupt-checksum rejection before extraction, installed-binary preservation, permissions, and staging cleanup. Keep real pinned SecretSpec scope/multiline round trips and safe timeout/missing-binary/provider-error handling; mocks alone do not replace that integration boundary.
- [ ] Replace Python emulation of JavaScript regex semantics in Renovate tests with a native Node invocation of configured regexes. Derive operator-tool expected versions from their source annotations/defaults; preserve BWS-specific tag filtering.
- [ ] Run `pytest tests/unit tests/integration` and compare scenario coverage with the migration checklist before deleting migrated suites.

## Task 3: Replace structural contracts with real role behavior

**Files:** Ansible role-contract tests/policy, runtime Talos/Restic roles, and pytest integration scenarios.

**Consumes:** Task 2 execution fixtures. **Produces:** Operational safety coverage independent of task names, literal Jinja expressions, and task layout; production roles without test-only execution switches.

- [ ] Run complete role entry points. Stop selecting/copying tasks by indexes, display names, include filenames, or serialized variable references for test execution.
- [ ] Cover Restic app/all planning, exclusions, missing apps/PVCs, multiple workloads, selected snapshots, and original replica/sync-policy state, including originally absent policies.
- [ ] Record restore operations and require pause/scale-down before deletion, planned paths and snapshot selectors, PVC-root preservation, and successful original-state restoration. Unsafe roots must be rejected before pod exec. Inject failure in prepare, restore, resume, and cleanup; preserve current paused or partially resumed state and inspection evidence, with no automatic destructive retry/resume.
- [ ] Cover zero/multiple ApplicationSet matches, recorded present/absent original policy, scoped stale Job/Pod deletion and wait failures, and success-only restore-job removal. Unrelated jobs, pods, apps, namespaces, PVCs, and original replica values must remain untouched.
- [ ] Exercise confirmed and unconfirmed restores in ordinary/check mode, including direct restore entry points. Use a test-only pod-exec module boundary for the unsupported transport; never execute destructive fixture commands on the host.
- [ ] Exercise Talos generation/validation, exact server version independent of client version, private file permissions, cleanup on generation/validation failure, bootstrap preflight/order, warmup cleanup, and propagated native failures. Keep direct filesystem deletion semantics covered by disposable-file scenarios.
- [ ] Cover check-mode nonmutation for every Talos mutating role entry point: generation, apply, bootstrap, reset, Talos upgrade, and Kubernetes upgrade. Record command/API effects and inspect temporary filesystem outputs; generate all targets from synthetic inputs and current role defaults rather than copied pins.
- [ ] Include platform wait/destroy native failure/timeout behavior and warmup cleanup failure, and Argo refresh all-app/single-app/missing-app scope. Cover Terraform plan/apply missing credentials before invocation, exact scoped delivered inputs with no machine tokens, and native sensitivity rather than literal HCL spellings. Fake boundaries must fail on unexpected targets/operations, not acknowledge everything.
- [ ] Replace structural checks for credential mappings and no_log with recorded delivered environments/arguments and sentinel-redaction scenarios on success and failure. Keep runtime input assertions.
- [ ] Only after normal-path fixture coverage passes, remove Talos/Restic `*_test_mode` defaults and branches and their test-only input variables. Preserve ordinary role behavior and operator arguments.
- [ ] Demonstrate representative removed-guard, wrong-target, reordered-phase, masked-failure, and wrong-version mutations fail the new suite. Harmless task renaming/addition must pass. Remove static operation catalogs, flattening, and their dedicated runner.

## Task 4: Replace all configuration policy with plain pytest

**Files:** All five existing policy trees, repository/Kubernetes validation roles, source-inventory templates, and new configuration tests.

**Consumes:** Shared parsed source objects. **Produces:** Configuration assertions with source/resource identifiers in failures, and native Kubernetes artifacts for rendered checks.

- [ ] For each rule, identify its operational purpose. Move syntax/style/schema checks to native tooling, migrate necessary configuration relationships, replace execution checks with Task 3 scenarios, and remove only proven redundant checks.
- [ ] Read YAML/TOML/JSON5/HCL directly. Preserve tracked-source boundaries for Terraform and exclude private/generated files. Reject duplicate/malformed inputs where the current contract requires rejection; never silently substitute an empty document.
- [ ] Preserve parsed key order and explicit vendored exceptions for source conventions; current native formatters/yamllint do not prove field ordering, so retain those simple assertions. Preserve optional-section behavior, valid extra distinct providers, IPv6 browser URLs, and semantic-version/prerelease comparisons without accidental type coercion or new literal version copies.
- [ ] Cover metadata/chart declarations/sync waves, generated-name uniqueness, source conventions, app-template compatibility, credential ownership/scopes, Talos targets, provider compatibility, application wiring, gateway/network relationships, and Gatus coverage.
- [ ] Replace copied addresses/ports/versions with comparisons to owning values. Preserve application-specific requirements such as health endpoints, shared-media ownership, VPN probes/firewall wiring, and known compatibility constraints.
- [ ] Remove the repository inventory adapter, giant Kubernetes policy-inventory template, task-position/flag inspection, and route-coverage JSON round trip once their source/behavior checks pass. Retain small safe loaders and legitimate embedded-document parsing.
- [ ] Refactor the Ansible Kubernetes role to use the caller-owned workspace interface above and minimal original chart metadata. Keep CRD-inclusive rendering, served-schema precedence, catalog fallback, fail-closed schema behavior, existing documented exclusions, and raw/rendered deprecation checks.
- [ ] Run rendered resource assertions over actual output, including init containers and effective pod/container security contexts. Missing rendered apps/resources fail instead of becoming skipped/empty test parameters.
- [ ] Exercise native validation pipeline behavior with synthetic chart/CRD inputs and controlled tool boundaries, replacing policy that inspects command strings/order. Verify malformed/missing/conflicting schemas and invalid/unknown resource fields using the real exporter/validator where applicable.
- [ ] Run configuration tests and representative invalid fixtures; then remove all Rego files, Conftest calls, and policy-specific playbooks/roles. Keep Git artifact checks in repository pytest tests invoking Git itself.
- [ ] Check ignored credential/recovery/backups as well as tracked credential rejection with native Git commands. Keep generated/private Terraform exclusion and the requirement to stage new Terraform sources before the source gate; fixture mutations occur only in disposable repository copies.

## Task 5: Unify Task commands, CI, and dependencies

**Files:** Taskfile, CI workflow/toolchain setup, dependency declarations, and Renovate configuration.

**Consumes:** Tasks 2–4 suites and Kubernetes workspace interface. **Produces:** The command contract above, with matching local and CI coverage and no nested test runners.

- [ ] Implement `task test`, the focused commands, and the full aggregate exactly as specified above. Confirm each pytest subset runs once in full local validation.
- [ ] During Tasks 1–4, wire each completed migrated subset into its existing focused local/CI gate in the same commit, before removing the old invocation. Preserve a passing gate after each migration; Task 5 performs final consolidation, not the first connection of new checks to CI. Transitional coexistence is permitted until coverage is verified.
- [ ] Keep CI Format and Static Analysis native checks. In Ansible run `lint:ansible`, `lint:repository`, and `lint:wiki`; in Kubernetes run `lint:kubernetes`; keep native Terraform validation and Quality Gate.
- [ ] Remove Conftest installation/pins/manager references and obsolete wrapper setup. Keep the real SecretSpec install needed for its executable integration coverage, deriving its expected version from the role pin.
- [ ] Add Node 24 to the Ansible toolchain profile for native Renovate-regex tests; retain OpenTofu and pinned SecretSpec there. Keep Helm/kubeconform/Pluto in the Kubernetes profile, and ensure the integration subset does not request their real pipeline fixture. Document the matching local Node prerequisite and Python/collection paths after test relocation.
- [ ] Verify focused commands independently from a populated clean dependency environment, and verify their combined test coverage equals `task test`. Missing prerequisites fail clearly, not via conditional skips.
- [ ] Compare collected pytest node IDs for the disjoint focused subsets against full-suite collection without pinning a permanent count. Run focused gates in arbitrary order and twice to confirm independent fixture state, output ownership, and lack of order-sensitive cached facts; this is migration acceptance, not a new routine repeated-test gate.
- [ ] Validate Renovate configuration and extraction for newly pinned dependencies and existing operator tool pins after file moves; use native extraction for delivery verification.

## Task 6: Documentation, final audit, and handoff

**Files:** README, root and wiki agent guidance, contributor workflow, testing-boundary explanation, validation architecture/decision pages, affected operational wiki pages, source catalog/index, and wiki log.

- [ ] Replace the former policy guide with `tests/README.md`, a concise guide describing native tools, configuration/unit/integration checks, focused commands, fixture ownership, and when a check is warranted. Update root/wiki agent guidance, the wiki source catalog/index as affected, README prerequisites/layout, and all local source links after removing `policy` and moving `ansible/tests`.
- [ ] Explain the absence of Rego/Conftest and test-mode switches, and retain the distinction between offline validation and live deployment acceptance.
- [ ] Review related backup/restore, Talos, secrets, uptime, and Renovate pages for changed procedures. Recheck the wiki log at execution time: October's semantic review is already recorded, but a later month's first substantive PR must perform its required review if no entry exists.
- [ ] Audit the entire repository for obsolete test paths, conftest CLI references, Rego, static operation catalogs, test-mode flags, version duplication, nested test discovery, and CI-only assertions. The pytest fixture filename `conftest.py` is intentional.
- [ ] Run `task fmt`, `task lint`, and `git diff --check`; confirm the migration checklist covers every old safeguard and that no operator/runtime behavior changed unintentionally.
- [ ] Report remaining focused Python adapters, their purpose, and any behavior that remains unverified. No implementation success claim until the full gate passes.
- [ ] Report the before/after repository-owned validation code and runner layers. Require a net reduction in maintained plumbing, consolidate duplicated assertions, and retain separate tests only when they cover a distinct input or execution boundary; do not mechanically translate all 208 cases into equally verbose Python.
- [ ] Deliver implementation through a PR with wiki impact and verification evidence. Merge and live operations require their separately authorized workflow; this plan does not request either.

## Completion criteria

- One pytest runner owns all repository configuration, adapter, and Ansible behavior tests; native tools retain their specialized checks.
- No Conftest CLI/Rego, policy-normalization inventories, source-task execution reconstruction, or Ansible wrappers that launch test discovery remain. Small generic source-content checks remain ordinary pytest assertions.
- Production roles contain no test-only execution mode. Small fixture playbooks invoke actual role entry points with controlled boundaries.
- Tests enforce observable safety and cross-file relationships rather than equivalent source spelling, display names, or duplicated dependency versions.
- The full local gate and CI cover the same cases without routine duplicate execution, and documentation describes the final architecture.
- Operator interfaces, restore/check-mode/rollback/redaction/cleanup protections, compatibility, and schema/route coverage retain demonstrated coverage, including valid and invalid regression inputs and failure-boundary evidence. Every baseline case has a documented disposition; no required test silently skips.
