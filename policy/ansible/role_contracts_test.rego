package main

import rego.v1

role_inventory(documents) := {"kind": "ansible-role-inventory", "documents": documents, "flat": []}

test_missing_restore_transaction_is_denied if {
  result := deny with input as role_inventory({})
  "Missing or ambiguous safety operation: restore_transaction" in result
}

test_duplicate_scale_operations_are_denied if {
  scale := {"kubernetes.core.k8s_scale": {"replicas": 0}}
  result := deny with input as role_inventory({"restic/tasks/execute_prepare_app.yml": [scale, scale]})
  "Missing or ambiguous safety operation: scale_down" in result
}

test_restore_resumes_only_after_data_restore if {
  tasks := [{"ansible.builtin.include_tasks": "execute_prepare_app.yml"}, {"ansible.builtin.include_tasks": "execute_resume_app.yml"}, {"ansible.builtin.include_tasks": "execute_restore_app.yml"}]
  result := deny with input as role_inventory({"restic/tasks/execute.yml": [{"block": tasks}]})
  "Restore phase order changed" in result
}

test_original_workload_replicas_are_required if {
  tasks := [{"kubernetes.core.k8s_scale": {"replicas": 1}}]
  result := deny with input as role_inventory({"restic/tasks/execute_resume_app.yml": tasks})
  "Safety field changed: scale_up.kubernetes.core.k8s_scale.replicas" in result
}

test_restore_rescue_must_not_resume_workloads if {
  tasks := [{"block": [{"ansible.builtin.include_tasks": "execute_prepare_app.yml"}], "rescue": [{"ansible.builtin.fail": {"msg": "failed"}}, {"kubernetes.core.k8s_scale": {"replicas": 1}}]}]
  result := deny with input as role_inventory({"restic/tasks/execute.yml": tasks})
  "Restore failure branches must fail without mutation" in result
}

test_restore_rescue_must_propagate_failure if {
  tasks := [{"block": [{"ansible.builtin.include_tasks": "execute_prepare_app.yml"}], "rescue": [{"ansible.builtin.debug": {"msg": "failed"}}]}]
  result := deny with input as role_inventory({"restic/tasks/execute.yml": tasks})
  "Restore failure branches must fail without mutation" in result
}

test_restore_delete_guard_rejects_root if {
  task := {"ansible.builtin.assert": {"that": ["item is match('^/')"]}, "loop": "{{ restic_restore_app_plan.restore_paths }}"}
  result := deny with input as role_inventory({"restic/tasks/execute_prepare_app.yml": [task]})
  "Restore delete path guard accepts unsafe roots" in result
}

test_restore_delete_guard_accepts_scoped_paths if {
  task := {"ansible.builtin.assert": {"that": ["item is match('^/restore/data/appdata/.+')"]}, "loop": "{{ restic_restore_app_plan.restore_paths }}"}
  result := deny with input as role_inventory({"restic/tasks/execute_prepare_app.yml": [task]})
  not "Restore delete path guard accepts unsafe roots" in result
}

test_native_wait_rejects_custom_failure_override if {
  task := {"kubernetes.core.k8s_info": {"wait": true, "wait_condition": {"type": "Available"}, "wait_timeout": 60, "wait_sleep": 1}, "failed_when": false}
  result := deny with input as role_inventory({"platform/tasks/wait_condition.yml": [task]})
  "Safety field must be absent: platform_wait.failed_when" in result
}

test_talos_cleanup_is_guarded_on_tempfile_creation if {
  cleanup := {"ansible.builtin.file": {"path": "{{ talos_generate_secrets_temp.path | default('') }}", "state": "absent"}}
  task := {"block": [{"ansible.builtin.tempfile": {"state": "file"}}], "always": [cleanup]}
  result := deny with input as role_inventory({"talos/tasks/generate.yml": [task]})
  "Safety field changed: talos_secret_cleanup.when" in result
}

test_tofu_forbids_unscoped_machine_tokens if {
  every token in ["BWS_ACCESS_TOKEN", "BW_ACCESS_TOKEN"] {
    mutated := object.union(terraform_fixture[1], {"environment": object.union(terraform_fixture[1].environment, {token: "fixture"})})
    result := deny with input as layout_inventory([terraform_fixture[0], mutated], [bitwarden_fixture])
    sprintf("Terraform plan must not receive %s", [token]) in result
  }
}

test_inherited_failure_masking_is_denied if {
  inventory := {"flat": [{"source": "talos/tasks/generate.yml", "task": {"ansible.builtin.file": {"state": "absent"}}, "protected": true, "guards": ["not ansible_check_mode"], "failure_masked": true}], "documents": {}}
  result := deny with input as inventory
  "Safety operation inherits failure masking: talos/tasks/generate.yml" in result
}

test_restore_safe_failure_branch_is_allowed if {
  tasks := [{"block": [{"ansible.builtin.include_tasks": "execute_prepare_app.yml"}], "rescue": [{"ansible.builtin.debug": {"msg": "inspect"}}, {"ansible.builtin.fail": {"msg": "failed"}}]}]
  result := deny with input as role_inventory({"restic/tasks/execute.yml": tasks})
  not "Restore failure branches must fail without mutation" in result
}

test_restore_always_must_not_delete_evidence if {
  tasks := [{"block": [{"ansible.builtin.include_tasks": "execute_prepare_app.yml"}], "rescue": [{"ansible.builtin.fail": {"msg": "failed"}}], "always": [{"kubernetes.core.k8s": {"kind": "Job", "state": "absent"}}]}]
  result := deny with input as role_inventory({"restic/tasks/execute.yml": tasks})
  "Restore failure branches must fail without mutation" in result
}

test_native_wait_with_required_fields_is_allowed if {
  task := {"kubernetes.core.k8s_info": {"wait": true, "wait_condition": {"type": "Available"}, "wait_timeout": 60, "wait_sleep": 1}}
  result := deny with input as role_inventory({"platform/tasks/wait_condition.yml": [task]})
  not "Safety field changed: platform_wait.kubernetes.core.k8s_info.wait" in result
  not "Safety field missing: platform_wait.kubernetes.core.k8s_info.wait_condition.type" in result
  not "Safety field must be absent: platform_wait.failed_when" in result
}

test_delete_contents_must_preserve_pvc_roots if {
  every command in ["rm -rf -- '{{ item }}'", "sh -ceu \"rm -rf '{{ item }}'\"", "sh -ceu \"find '{{ item }}' -exec rm -rf -- {} +;\""] {
    task := {"kubernetes.core.k8s_exec": {"command": command}}
    result := deny with input as role_inventory({"restic/tasks/execute_prepare_app.yml": [task]})
    "Restore deletion must preserve PVC roots" in result
  }
}

test_scoped_contents_deletion_is_allowed if {
  task := {"kubernetes.core.k8s_exec": {"command": "sh -ceu \"if [ -d '{{ item }}' ]; then find '{{ item }}' -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +; else mkdir -p '{{ item }}'; fi\""}}
  result := deny with input as role_inventory({"restic/tasks/execute_prepare_app.yml": [task]})
  not "Restore deletion must preserve PVC roots" in result
}

snapshot_restore_command := "restic --retry-lock {{ restic_restore_retry_lock }} restore {{ restic_restore_effective_snapshot }} --host {{ restic_restore_snapshot_host }} --tag {{ restic_restore_snapshot_tag }} --path {{ restic_restore_snapshot_path }} {{ restic_restore_app_plan.pvc_paths }} --exclude-xattr '*' --target {{ restic_restore_target_root }}"

test_snapshot_restore_with_all_scopes_is_allowed if {
  task := {"kubernetes.core.k8s_exec": {"command": snapshot_restore_command}}
  result := deny with input as role_inventory({"restic/tasks/execute_restore_app.yml": [task]})
  not "Restore command must retain selected snapshot and planned PVC paths" in result
}

test_snapshot_restore_rejects_changed_or_duplicate_scope if {
  every command in [replace(snapshot_restore_command, "--host {{ restic_restore_snapshot_host }}", ""), concat(" ", [snapshot_restore_command, "--target /"]), replace(snapshot_restore_command, "{{ restic_restore_effective_snapshot }}", "latest")] {
    task := {"kubernetes.core.k8s_exec": {"command": command}}
    result := deny with input as role_inventory({"restic/tasks/execute_restore_app.yml": [task]})
    "Restore command must retain selected snapshot and planned PVC paths" in result
  }
}

test_restore_original_sync_policy_is_required if {
  task := {"kubernetes.core.k8s": {"definition": {"kind": "Application", "spec": {"syncPolicy": {"automated": {}}}}}}
  result := deny with input as role_inventory({"restic/tasks/execute_resume_app.yml": [task]})
  "Safety field changed: restore_app_sync.kubernetes.core.k8s.definition.spec.syncPolicy" in result
}

test_scaling_must_use_original_workload_identity if {
  task := {"kubernetes.core.k8s_scale": {"name": "fixed-app", "replicas": "{{ item.replicas }}"}}
  result := deny with input as role_inventory({"restic/tasks/execute_resume_app.yml": [task]})
  "Safety field changed: scale_up.kubernetes.core.k8s_scale.name" in result
}

warmup_fixture(name, namespace) := {"block": [{"kubernetes.core.k8s": {"definition": {"kind": "Pod", "metadata": {"name": "warmup", "namespace": "kube-system"}}}}], "always": [{"kubernetes.core.k8s": {"kind": "Pod", "name": name, "namespace": namespace, "state": "absent", "wait": true}}]}

test_warmup_cleanup_retains_created_pod_identity if {
  every fixture in [[warmup_fixture("other", "kube-system"), "k8tz cleanup must delete the created warmup pod"], [warmup_fixture("warmup", "other"), "k8tz cleanup namespace must match the created warmup pod"]] {
    result := deny with input as role_inventory({"platform/tasks/k8tz_warmup.yml": [fixture[0]]})
    fixture[1] in result
  }
}

test_warmup_cleanup_same_identity_is_allowed if {
  result := deny with input as role_inventory({"platform/tasks/k8tz_warmup.yml": [warmup_fixture("warmup", "kube-system")]})
  not "k8tz cleanup must delete the created warmup pod" in result
  not "k8tz cleanup namespace must match the created warmup pod" in result
}

talos_command_fixture(gen, validate) := {"no_log": true, "when": "not ansible_check_mode", "block": [{"ansible.builtin.tempfile": {"state": "file"}}, {"ansible.builtin.command": {"argv": gen}}, {"ansible.builtin.command": {"argv": validate}}]}

test_talos_generation_and_metal_validation_are_required if {
  every commands in [[["wrong", "gen", "config"], ["talosctl", "validate", "--mode", "metal"]], [["talosctl", "gen", "wrong"], ["talosctl", "validate", "--mode", "metal"]], [["talosctl", "gen", "config"], ["talosctl", "validate", "--mode", "container"]], [["talosctl", "gen", "config"], ["talosctl", "validate", "metal"]]] {
    result := deny with input as role_inventory({"talos/tasks/generate.yml": [talos_command_fixture(commands[0], commands[1])]})
    "Talos generation must generate and validate metal configuration" in result
  }
}

test_talos_generation_valid_commands_are_allowed if {
  result := deny with input as role_inventory({"talos/tasks/generate.yml": [talos_command_fixture(["talosctl", "gen", "config"], ["talosctl", "validate", "--mode", "metal"])]})
  not "Talos generation must generate and validate metal configuration" in result
}

test_talos_transaction_retains_confidentiality_and_check_mode if {
  every fixture in [[{"block": [{"ansible.builtin.tempfile": {}}], "no_log": false, "when": "not ansible_check_mode"}, "Safety field changed: talos_transaction.no_log"], [{"block": [{"ansible.builtin.tempfile": {}}], "no_log": true, "when": "ansible_check_mode or true"}, "Talos generation transaction requires its check mode guard"]] {
    result := deny with input as role_inventory({"talos/tasks/generate.yml": [fixture[0]]})
    fixture[1] in result
  }
}

test_talos_temp_files_are_deleted_in_always if {
  every variable in ["talos_generate_secrets_temp", "talos_generate_output"] {
    task := {"block": [{"ansible.builtin.tempfile": {}}], "always": [{"ansible.builtin.file": {"path": sprintf("{{ %s.path | default('') }}", [variable]), "state": "present"}, "when": sprintf("%s is defined", [variable])}]}
    result := deny with input as role_inventory({"talos/tasks/generate.yml": [task]})
    operation := {"talos_generate_secrets_temp": "talos_secret_cleanup", "talos_generate_output": "talos_output_cleanup"}[variable]
    sprintf("Safety field changed: %s.ansible.builtin.file.state", [operation]) in result
  }
}

test_bootstrap_preserves_dependency_order if {
  tasks := [{"ansible.builtin.import_tasks": "argocd.yml"}, {"ansible.builtin.include_tasks": "install_release_with_manifests.yml"}, {"ansible.builtin.include_tasks": "install_release.yml"}, {"ansible.builtin.import_tasks": "external_secrets.yml"}]
  result := deny with input as role_inventory({"platform/tasks/bootstrap.yml": tasks})
  "Platform bootstrap dependency order changed" in result
}

test_bootstrap_order_accepts_unrelated_tasks if {
  tasks := [{"ansible.builtin.include_tasks": "install_release_with_manifests.yml"}, {"ansible.builtin.debug": {"msg": "unrelated"}}, {"ansible.builtin.include_tasks": "install_release.yml"}, {"ansible.builtin.import_tasks": "external_secrets.yml"}, {"ansible.builtin.import_tasks": "argocd.yml"}]
  result := deny with input as role_inventory({"platform/tasks/bootstrap.yml": tasks})
  not "Platform bootstrap dependency order changed" in result
}

restore_block_inventory(tasks) := role_inventory({"restic/tasks/execute.yml": [{"block": array.concat(tasks, [{"ansible.builtin.include_tasks": "execute_prepare_app.yml"}])}]})

test_applicationset_original_policy_must_be_recorded if {
  task := {"ansible.builtin.set_fact": {"restic_restore_applicationset_original_sync_policy": "{{ unrelated_policy }}"}}
  result := deny with input as restore_block_inventory([task])
  "ApplicationSet original sync policy must come from the recorded resource" in result
}

test_applicationset_must_pause_updates_and_remove_only_temporary_policy if {
  every fixture in [[{"kubernetes.core.k8s": {"definition": {"spec": {"syncPolicy": {"applicationsSync": "sync"}}}}}, "Safety field changed: applicationset_pause.kubernetes.core.k8s.definition.spec.syncPolicy.applicationsSync"], [{"kubernetes.core.k8s_json_patch": {"kind": "ApplicationSet", "patch": [{"op": "remove", "path": "/spec"}]}}, "Safety field changed: applicationset_remove_policy.kubernetes.core.k8s_json_patch.patch"], [{"kubernetes.core.k8s": {"definition": {"spec": {"syncPolicy": "{{ restic_restore_applicationset_original_sync_policy }}"}}}, "when": "true"}, "Safety field changed: applicationset_restore.when"]] {
    result := deny with input as restore_block_inventory([fixture[0]])
    fixture[1] in result
  }
}

test_applicationset_read_guard_is_required if {
  result := deny with input as restore_block_inventory([{"ansible.builtin.assert": {"that": ["true"]}}])
  "Missing or ambiguous safety operation: applicationset_guard" in result
}

test_restore_phases_must_use_recorded_plan if {
  every phase in [["execute_prepare_app.yml", "prepare_apps"], ["execute_restore_app.yml", "restore_apps"], ["execute_resume_app.yml", "resume_apps"]] {
    tasks := [{"ansible.builtin.include_tasks": "execute_prepare_app.yml", "loop": "{{ restic_restore_plan }}", "loop_control": {"loop_var": "restic_restore_app_plan"}} | phase[0] != "execute_prepare_app.yml"]
    changed := {"ansible.builtin.include_tasks": phase[0], "loop": "{{ another_plan }}", "loop_control": {"loop_var": "another_app"}}
    inventory := role_inventory({"restic/tasks/execute.yml": [{"block": array.concat(tasks, [changed])}]})
    result := deny with input as inventory
    sprintf("Safety field changed: %s.loop", [phase[1]]) in result
    sprintf("Safety field changed: %s.loop_control.loop_var", [phase[1]]) in result
  }
}

test_stale_restore_job_and_pods_remain_scoped_and_wait_for_deletion if {
  every fixture in [[{"kubernetes.core.k8s": {"kind": "Job", "name": "other", "namespace": "other", "wait": false}}, "Safety field changed: stale_job_delete.kubernetes.core.k8s.name"], [{"kubernetes.core.k8s": {"kind": "Job", "namespace": "other"}}, "Safety field changed: stale_job_delete.kubernetes.core.k8s.namespace"], [{"kubernetes.core.k8s": {"kind": "Job", "wait": false}}, "Safety field changed: stale_job_delete.kubernetes.core.k8s.wait"], [{"kubernetes.core.k8s_info": {"kind": "Pod", "label_selectors": ["app=restic"]}}, "Safety field changed: stale_pod_read.kubernetes.core.k8s_info.label_selectors"], [{"kubernetes.core.k8s": {"kind": "Pod", "namespace": "other"}}, "Safety field changed: stale_pod_delete.kubernetes.core.k8s.namespace"], [{"kubernetes.core.k8s": {"kind": "Pod", "name": "arbitrary"}}, "Safety field changed: stale_pod_delete.kubernetes.core.k8s.name"]] {
    result := deny with input as role_inventory({"restic/tasks/execute.yml": [fixture[0]]})
    fixture[1] in result
  }
}

test_prepare_and_resume_order_retain_original_state if {
  tasks := [{"kubernetes.core.k8s": {"definition": {"kind": "Application", "spec": {"syncPolicy": "{{ restic_restore_app_plan.sync_policy }}"}}}}, {"kubernetes.core.k8s_scale": {"replicas": "{{ item.replicas }}"}}]
  result := deny with input as role_inventory({"restic/tasks/execute_resume_app.yml": tasks})
  "Safety order changed: scale_up before restore_app_sync" in result
}

test_warmup_cleanup_rejects_missing_created_metadata if {
  task := {"block": [{"kubernetes.core.k8s": {"definition": {"kind": "Pod"}}}], "always": [{"kubernetes.core.k8s": {"kind": "Pod", "name": "warmup", "namespace": "kube-system", "state": "absent", "wait": true}}]}
  result := deny with input as role_inventory({"platform/tasks/k8tz_warmup.yml": [task]})
  "k8tz cleanup must delete the created warmup pod" in result
  "k8tz cleanup namespace must match the created warmup pod" in result
}


test_warmup_cleanup_rejects_missing_created_identity_fields if {
  every fixture in [[{"name": "warmup"}, "k8tz cleanup namespace must match the created warmup pod"], [{"namespace": "kube-system"}, "k8tz cleanup must delete the created warmup pod"]] {
    task := {"block": [{"kubernetes.core.k8s": {"definition": {"kind": "Pod", "metadata": fixture[0]}}}], "always": [{"kubernetes.core.k8s": {"kind": "Pod", "name": "warmup", "namespace": "kube-system", "state": "absent", "wait": true}}]}
    result := deny with input as role_inventory({"platform/tasks/k8tz_warmup.yml": [task]})
    fixture[1] in result
  }
}

test_warmup_cleanup_rejects_missing_cleanup_identity_fields if {
  every fixture in [[{"kind": "Pod", "name": "warmup"}, "k8tz cleanup namespace must match the created warmup pod"], [{"kind": "Pod", "namespace": "kube-system"}, "k8tz cleanup must delete the created warmup pod"]] {
    task := {"block": [{"kubernetes.core.k8s": {"definition": {"kind": "Pod", "metadata": {"name": "warmup", "namespace": "kube-system"}}}}], "always": [{"kubernetes.core.k8s": fixture[0]}]}
    result := deny with input as role_inventory({"platform/tasks/k8tz_warmup.yml": [task]})
    fixture[1] in result
  }
}
