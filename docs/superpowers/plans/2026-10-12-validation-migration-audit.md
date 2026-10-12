# Validation migration audit

One-time review appendix for the migration from `e66f8dac`. This is not a runtime
contract registry. Each baseline test below is accounted for by behavior, direct
configuration checks, native validation, or removal of its superseded adapter API.
Equivalent-expression and catalog-shape rejection tests intentionally disappear;
their operational safeguards are covered through actual entry points.

## Python modules

### test_crd_schemas.py

Disposition: tests/unit/test_crd_schemas.py.

- `test_strict_schema_checks_types_unknown_fields_and_property_named_properties`
- `test_constraint_branches_preserve_parent_properties`
- `test_kubernetes_nullable_and_int_or_string_semantics`
- `test_missing_or_malformed_served_schema_fails`
- `test_conflicting_definitions_fail_identical_duplicates_work`
- `test_chart_label_selector_default_equals_is_a_safe_scalar`
- `test_route_parser_uses_safe_kubernetes_yaml_dialect`

### test_operator_patterns.py

Disposition: tests/integration/test_restore.py, test_talos.py, test_tools.py (whole entrypoints).

- `test_confirmed_restore_check_mode_skips_execution`
- `test_direct_restore_exec_is_skipped_in_check_mode`
- `test_server_version_is_exact_and_independent_of_client`
- `test_operator_validation_tracks_configured_secretspec_pin`

### test_renovate.py

Disposition: tests/unit/test_renovate.py (native Node regexes).

- `test_operator_pins_are_discovered_from_their_own_annotations`
- `test_sdk_release_filter_accepts_only_bws_versions`

### test_repository_inventory.py

Disposition: tests/config/repository/test_conventions.py (tracked HCL/private exclusion, JSON5), test_configuration.py (project normalization), Kubernetes pipeline behavior tests; flatten/position inventory API cases retired.

- `test_task_discovery_does_not_depend_on_display_names`
- `test_non_bws_uri_cannot_be_normalized_as_a_valid_project`
- `test_project_normalization_uses_synthetic_uuids`
- `test_disposable_root_reads_tracked_hcl_and_normalizes_repository_sources`
- `test_schema_flags_from_task_block_or_sibling_fact_reach_policy`

### test_role_contracts.py

Disposition: tests/integration native safety scenarios and one-off removed-guard/reorder/wrong-target/renaming mutations; inventory-only rejection cases retired with their runner.

- `test_renamed_operations_and_harmless_added_tasks_are_allowed`
- `test_unsafe_restore_changes_are_rejected`
- `test_inventory_preserves_inherited_guards_and_failure_masking`
- `test_missing_critical_task_document_is_rejected`
- `test_missing_warmup_pod_metadata_is_rejected`

### test_secret_delivery.py

Disposition: tests/unit/test_secret_delivery.py and tests/integration/test_secret_delivery.py.

- `test_root_requires_every_source_revision_and_sync`
- `test_ready_requires_fresh_valid_timestamp`
- `test_provider_json_parser_never_surfaces_malformed_payload`
- `test_only_children_owned_by_expected_appset_count`
- `test_task_clears_inherited_credentials_and_preserves_operator_settings`

### test_secrets.py

Disposition: tests/unit/test_secrets.py and tests/integration/test_secrets.py.

- `test_round_trip_multiline_special_characters`
- `test_duplicate_names_rejected`
- `test_refuse_write_and_argument_injection`
- `test_provider_error_redacted`
- `test_malformed_and_wrong_shape_rejected`
- `test_timeout_and_missing_binary_safe`
- `test_real_secretspec_scope_and_multiline_preservation`

### test_talos_generation.py

Disposition: tests/integration/test_talos.py and test_platform.py.

- `test_fresh_generation_custom_paths_and_versions`
- `test_generation_failure_cleans_temporary_secrets`
- `test_cluster_preflight_denial_never_contacts_node`
- `test_malformed_material_is_redacted_and_generation_never_runs`

### test_terraform.py

Disposition: tests/integration/test_terraform.py (parsed HCL, native console).

- `test_zone_input_stays_public_and_preserves_resource_state_sensitivity`

## YAML suites

| Retired suite | Replacement |
| --- | --- |
| cluster-secrets | pytest provider/token/handoff parameters with lifecycle-owned API |
| secret-unit | wrapper removed; pytest discovers adapter units directly |
| secrets-setup | real setup role: selected/default tools, checksums, staging and binary preservation |
| native-conventions | real tofu clean role on disposable files, ordinary/check mode |
| restic-restore | live API app/all planning and complete transaction scenarios |
| talos-upgrade | real upgrade entrypoint, installer and exact server tag |
| source-inventory | typed source discovery, safe embedded parsing and configuration assertions; JSON inventory removed |
| uptime | raw/rendered URL-host coverage, missing/obsolete/duplicate negatives; temporary JSON inventory removed |
| wiki-contracts | eight real wiki-role scenarios |

## Rego regression cases

### ansible/role_contracts_test.rego

Disposition: tests/integration/test_restore.py, test_talos.py, test_tools.py, test_platform.py, test_bootstrap.py, test_terraform.py. Operation uniqueness/positions and source-expression mutations retire with the catalog; recorded effects, event order, identities, states, confidentiality, and native failure checks replace them.

- `test_missing_restore_transaction_is_denied`
- `test_duplicate_scale_operations_are_denied`
- `test_restore_resumes_only_after_data_restore`
- `test_original_workload_replicas_are_required`
- `test_restore_rescue_must_not_resume_workloads`
- `test_restore_rescue_must_propagate_failure`
- `test_restore_delete_guard_rejects_root`
- `test_restore_delete_guard_accepts_scoped_paths`
- `test_native_wait_rejects_custom_failure_override`
- `test_talos_cleanup_is_guarded_on_tempfile_creation`
- `test_tofu_forbids_unscoped_machine_tokens`
- `test_inherited_failure_masking_is_denied`
- `test_restore_safe_failure_branch_is_allowed`
- `test_restore_always_must_not_delete_evidence`
- `test_native_wait_with_required_fields_is_allowed`
- `test_delete_contents_must_preserve_pvc_roots`
- `test_scoped_contents_deletion_is_allowed`
- `test_snapshot_restore_with_all_scopes_is_allowed`
- `test_snapshot_restore_rejects_changed_or_duplicate_scope`
- `test_restore_original_sync_policy_is_required`
- `test_scaling_must_use_original_workload_identity`
- `test_warmup_cleanup_retains_created_pod_identity`
- `test_warmup_cleanup_same_identity_is_allowed`
- `test_talos_generation_and_metal_validation_are_required`
- `test_talos_generation_valid_commands_are_allowed`
- `test_talos_transaction_retains_confidentiality_and_check_mode`
- `test_talos_temp_files_are_deleted_in_always`
- `test_bootstrap_preserves_dependency_order`
- `test_bootstrap_order_accepts_unrelated_tasks`
- `test_applicationset_original_policy_must_be_recorded`
- `test_applicationset_must_pause_updates_and_remove_only_temporary_policy`
- `test_applicationset_read_guard_is_required`
- `test_restore_phases_must_use_recorded_plan`
- `test_stale_restore_job_and_pods_remain_scoped_and_wait_for_deletion`
- `test_prepare_and_resume_order_retain_original_state`
- `test_warmup_cleanup_rejects_missing_created_metadata`
- `test_warmup_cleanup_rejects_missing_created_identity_fields`
- `test_warmup_cleanup_rejects_missing_cleanup_identity_fields`

### ansible/role_safety_test.rego

Disposition: tests/integration: all Talos check-mode entrypoints, direct restore exec guards, credentials before tofu, native scoped delivery, token transaction/redaction and failure evidence. Task-name/flag inheritance and duplicate catalog entries retire; behavior and harmless-renaming acceptance remain.

- `test_sensitive_task_requires_no_log`
- `test_secret_read_requires_no_log`
- `test_resolved_application_credentials_require_no_log`
- `test_retained_token_requires_no_log`
- `test_protected_secret_read_is_allowed`
- `test_talos_check_guard_rejects_weakened_guard`
- `test_talos_check_guard_accepts_inherited_guard`
- `test_missing_no_log_is_denied`
- `test_missing_talos_check_guard_is_denied`
- `test_missing_terraform_credential_is_denied`
- `test_missing_terraform_action_is_denied`
- `test_missing_terraform_module_is_denied`
- `test_restore_exec_requires_check_mode_guard`
- `test_restore_exec_accepts_inherited_check_mode_guard`
- `test_harmless_added_and_renamed_tasks_are_allowed`
- `test_terraform_assertion_must_precede_action`
- `test_duplicate_terraform_actions_are_denied`
- `test_terraform_credential_mapping_mutation_is_denied`
- `test_bitwarden_missing_and_duplicate_writes_are_denied`
- `test_bitwarden_token_mapping_mutation_is_denied`

### kubernetes/observability_test.rego

Disposition: tests/config/kubernetes/test_resources.py::test_specific_runtime_and_observability_guards; actual raw/rendered resources.

- `test_victoria_resources_are_rejected`
- `test_victoria_crds_are_rejected`
- `test_prometheus_operator_resources_are_rejected`
- `test_prometheus_operator_crds_are_rejected`
- `test_legacy_workloads_are_rejected`
- `test_gatus_sidecar_is_rejected`
- `test_legacy_prometheus_workload_is_rejected`
- `test_sidecar_discovery_annotation_is_rejected`
- `test_gatus_deployment_is_allowed`
- `test_istio_prometheus_telemetry_is_rejected`
- `test_cert_manager_public_metrics_listener_is_rejected`

### kubernetes/resource_hygiene_test.rego

Disposition: tests/config/kubernetes/test_resources.py (positive/negative resource hygiene, native raw/rendered schemas).

- `test_istio_validation_webhooks_must_fail_closed`
- `test_nfs_controller_must_not_run_snapshotter_without_snapshot_crds`
- `test_externalsecret_requires_canonical_secret_store`
- `test_pvc_storage_class_must_be_approved`
- `test_latest_image_tags_are_rejected`
- `test_external_secret_requires_store_kind`
- `test_populated_secret_denied`
- `test_empty_controller_secret_allowed`
- `test_store_namespace_restrictions_required`
- `test_namespace_order_is_not_a_security_difference`

### kubernetes/route_coverage_test.rego

Disposition: tests/config/kubernetes/test_resources.py route regression cases; test_rendered.py actual raw/rendered host sets; inventory-dispatch cases retired because no inventory evaluator exists.

- `test_route_coverage_accepts_deduplicated_routes`
- `test_route_coverage_rejects_missing`
- `test_route_coverage_rejects_obsolete`
- `test_route_coverage_rejects_duplicates`
- `test_route_coverage_requires_inventory_shape`
- `test_route_coverage_does_not_apply_to_manifests`

### kubernetes/routes_test.rego

Disposition: tests/config/kubernetes/test_resources.py (route and annotation regressions); test_rendered.py actual output.

- `test_httproute_requires_expected_hostname_and_parent_ref`
- `test_httproute_allows_unannotated_routes`
- `test_legacy_external_dns_annotations_are_rejected_on_any_resource`
- `test_shared_gateway_requires_modern_lan_target`
- `test_shared_gateway_allows_modern_lan_target`

### kubernetes/workload_security_test.rego

Disposition: tests/config/kubernetes/test_resources.py (effective security, init containers, exceptions, capabilities, shared media).

- `test_valid_app_template_workload_passes`
- `test_app_template_requires_single_replica`
- `test_app_template_requires_recreate_strategy`
- `test_app_template_requires_allow_privilege_escalation_false`
- `test_app_template_requires_drop_all_capabilities`
- `test_app_template_requires_run_as_non_root_by_default`
- `test_linuxserver_images_are_exempt_from_run_as_non_root`
- `test_tailscale_is_exempt_from_container_security_rules`
- `test_paperless_gpt_requires_entrypoint_capabilities`
- `test_gluetun_liveness_must_check_http_health`
- `test_shared_media_claim_requires_group_zero`

### metadata/app_metadata_test.rego

Disposition: tests/config/kubernetes/test_sources.py; tests/unit/test_sources.py; test_conventions.py (unique names).

- `test_valid_metadata_passes`
- `test_missing_metadata_file_denied`
- `test_missing_values_file_denied`
- `test_empty_values_file_denied`
- `test_missing_chart_repo_denied`
- `test_missing_chart_version_denied`
- `test_missing_chart_name_for_non_oci_repo_denied`
- `test_invalid_sync_wave_denied`
- `test_missing_sync_wave_denied`
- `test_ignore_differences_must_be_list`
- `test_ignore_differences_item_requires_group`
- `test_ignore_differences_item_requires_kind`
- `test_duplicate_generated_name_denied`

### repository/contracts_test.rego

Disposition: tests/config/repository; tests/integration/test_terraform.py native wiring/sensitivity; Kubernetes pipeline behavior tests. Inventory/position normalization cases retire with their adapter; discovery, parsing, schema-bypass and failure behavior remain checked.

- `test_additional_distinct_keyring_provider_is_allowed`
- `test_additional_provider_cannot_duplicate_an_owned_project`
- `test_valid_inventory`
- `test_reject_shared_or_invalid_project`
- `test_reject_provider_cache_and_non_keyring`
- `test_reject_optional_path_or_ambiguous_secret`
- `test_reject_changed_scopes_and_secret_ownership`
- `test_reject_provider_compatibility_and_legacy_reads`
- `test_reject_retired_workflows`
- `test_reject_upgrade_support_or_patch_drift`
- `test_reject_missing_or_reordered_schema_pipeline`
- `test_reject_missing_required_inventory`
- `test_reject_empty_required_inventory`
- `test_reject_malformed_upgrade_versions`
- `test_accept_scope_order_and_harmless_task_names`
- `test_reject_schema_bypass_from_task_block_or_sibling_fact`

### source/app_configuration_test.rego

Disposition: tests/config/kubernetes/test_sources.py (actual sources, typed negatives, embedded parser); native rendered/schema gate.

- `test_changedetection_rejects_subcharacter_input_limits`
- `test_app_karakeep_accepts_valid`
- `test_app_karakeep_rejects_browser_image_override`
- `test_app_karakeep_rejects_entrypoint_override`
- `test_app_karakeep_rejects_sandbox_disabled`
- `test_app_karakeep_rejects_rasterizer_disabled`
- `test_app_karakeep_rejects_debugging_override`
- `test_app_karakeep_rejects_browser_service_port_mismatch`
- `test_app_karakeep_rejects_missing_structure`
- `test_app_karakeep_rejects_malformed_structure`
- `test_app_arr_accepts_valid`
- `test_app_arr_rejects_unsafe_tmpdir`
- `test_app_arr_rejects_chown_capability`
- `test_app_arr_rejects_missing_structure`
- `test_app_arr_rejects_malformed_structure`
- `test_app_qbittorrent_accepts_valid`
- `test_app_qbittorrent_rejects_non_http_readiness`
- `test_app_qbittorrent_rejects_readiness_port_mismatch`
- `test_app_qbittorrent_rejects_blocked_health_port`
- `test_app_qbittorrent_rejects_missing_structure`
- `test_app_qbittorrent_rejects_malformed_structure`
- `test_app_jellyfin_accepts_valid`
- `test_app_jellyfin_rejects_wrong_liveness_port`
- `test_app_jellyfin_rejects_wrong_health_path`
- `test_app_jellyfin_rejects_missing_lan_address`
- `test_app_jellyfin_rejects_wrong_published_address`
- `test_app_jellyfin_rejects_missing_udp_discovery`
- `test_app_jellyfin_rejects_missing_structure`
- `test_app_jellyfin_rejects_malformed_structure`
- `test_app_changedetection_accepts_valid`
- `test_app_changedetection_rejects_empty_model`
- `test_app_changedetection_rejects_nonpositive_input_limit`
- `test_app_changedetection_rejects_legacy_api_base`
- `test_app_changedetection_rejects_disabled_llm_features`
- `test_app_changedetection_rejects_missing_secret_consumption`
- `test_app_changedetection_rejects_wrong_secret_store`
- `test_app_changedetection_rejects_wrong_api_key_template`
- `test_app_changedetection_rejects_wrong_shared_item`
- `test_app_changedetection_rejects_missing_structure`
- `test_app_changedetection_rejects_malformed_structure`
- `test_app_gatus_accepts_valid`
- `test_app_gatus_rejects_missing_health_targets`
- `test_app_gatus_rejects_missing_structure`
- `test_app_gatus_rejects_malformed_structure`
- `test_app_recyclarr_accepts_valid`
- `test_app_recyclarr_rejects_nonmapping_format_groups`
- `test_app_recyclarr_rejects_nonlist_group_additions`
- `test_app_recyclarr_rejects_missing_trash_id`
- `test_app_recyclarr_rejects_incompatible_series_naming`
- `test_app_recyclarr_rejects_incompatible_folder_naming`
- `test_app_recyclarr_rejects_incompatible_movie_naming`
- `test_app_recyclarr_rejects_missing_structure`
- `test_app_recyclarr_rejects_malformed_structure`
- `test_changedetection_rejects_malformed_duplicate_credential`
- `test_all_arr_apps_require_safe_tmpdir`
- `test_gatus_requires_both_special_health_paths`
- `test_karakeep_allows_omitted_optional_args`
- `test_recyclarr_checks_colliding_instance_names_in_both_services`
- `test_karakeep_accepts_ipv6_browser_url`

### source/app_template_values_test.rego

Disposition: tests/config/kubernetes/test_sources.py (supported majors, optional fields, primary wiring, security profiles).

- `test_optional_sections_do_not_require_unrelated_sections`
- `test_rejects_reversed_present_sections`
- `test_valid_app_template_values_pass`
- `test_shared_media_claim_accepts_non_root_with_group_zero`
- `test_shared_media_claim_rejects_group_1000`
- `test_other_namespaces_cannot_use_shared_media_profile`
- `test_requires_main_primary_controller`
- `test_rejects_invalid_controllers_across_supported_majors`
- `test_accepts_supported_chart_versions`
- `test_rejects_unsupported_or_malformed_chart_versions`

### source/argocd_source_test.rego

Disposition: tests/config/kubernetes/test_sources.py::test_argocd_route_ownership_and_browser_ipv6.

- `test_rejects_argocd_raw_httproute_manifests`

### source/gateway_test.rego

Disposition: tests/config/kubernetes/test_conventions.py::test_gateway_relationship_accepts_moved_address_and_rejects_mismatch.

- `test_gateway_address_can_change_with_its_network`
- `test_gateway_dns_must_match_its_network`

### source/manifest_conventions_test.rego

Disposition: tests/config/kubernetes/test_conventions.py (owned filename, parsed field order, optional spec, vendored exception).

- `test_valid_manifest_conventions_pass`
- `test_rejects_non_prefixed_manifest_filename`
- `test_rejects_non_canonical_manifest_field_order`
- `test_rejects_spec_after_other_top_level_fields`
- `test_allows_manifest_without_spec`
- `test_rejects_non_canonical_metadata_field_order`

## Acceptance evidence

- Existing full lint passed before migration; the migrated full gate subsequently passed 390 cases before final review strengthened coverage.
- Independent review identified three missing failure guards. Restore checks now observe the target Application pause before scaling/deletion and its retained failure state; Terraform checks omit each credential individually; bootstrap checks the exact credential Secret target and token payload. Disposable role mutations prove each strengthened check rejects its unsafe change.
- The secret API permits only discovered source-owned targets and the canonical token holder; the provider CLI rejects requests for the wrong project.
- Native actual chart/schema/deprecation validation passed with served CRDs and route checks.
- Real REST module tests preserve scoped mutation, rollback, original state, waits and failure evidence.
- Missing prerequisites/discovery fail; fixture processes and output belong to pytest.
- Live restore, websocket acceptance, and fresh-cluster/deployed behavior remain outside offline validation.
