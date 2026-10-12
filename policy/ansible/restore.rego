package main

import rego.v1

restore_required_fields := [
  ["stale_job_delete", ["kubernetes.core.k8s", "state"], "absent"],
  ["stale_job_delete", ["kubernetes.core.k8s", "wait"], true],
  ["stale_job_delete", ["kubernetes.core.k8s", "namespace"], "{{ restic_restore_namespace }}"],
  ["stale_pod_delete", ["kubernetes.core.k8s", "state"], "absent"],
  ["stale_pod_delete", ["kubernetes.core.k8s", "wait"], true],
  ["stale_pod_delete", ["kubernetes.core.k8s", "namespace"], "{{ restic_restore_namespace }}"],
  ["successful_job_delete", ["kubernetes.core.k8s", "state"], "absent"],
  ["successful_job_delete", ["kubernetes.core.k8s", "wait"], true],
  ["successful_job_delete", ["kubernetes.core.k8s", "namespace"], "{{ restic_restore_namespace }}"],
  ["stale_job_delete", ["kubernetes.core.k8s", "name"], "{{ restic_restore_job_name }}"],
  ["successful_job_delete", ["kubernetes.core.k8s", "name"], "{{ restic_restore_job_name }}"],
  ["stale_pod_read", ["kubernetes.core.k8s_info", "namespace"], "{{ restic_restore_namespace }}"],
  ["stale_pod_read", ["kubernetes.core.k8s_info", "label_selectors"], ["job-name={{ restic_restore_job_name }}"]],
  ["stale_pod_delete", ["kubernetes.core.k8s", "name"], "{{ item.metadata.name }}"],
  ["stale_pod_delete", ["loop"], "{{ restic_restore_stale_pods.resources | default([]) }}"],
  ["applicationset_pause", ["kubernetes.core.k8s", "definition", "spec", "syncPolicy", "applicationsSync"], "create-only"],
  ["applicationset_restore", ["kubernetes.core.k8s", "definition", "spec", "syncPolicy"], "{{ restic_restore_applicationset_original_sync_policy }}"],
  ["applicationset_restore", ["when"], "restic_restore_applicationset_had_sync_policy | bool"],
  ["applicationset_remove_policy", ["when"], "not (restic_restore_applicationset_had_sync_policy | bool)"],
  ["applicationset_remove_policy", ["kubernetes.core.k8s_json_patch", "patch"], [{"op": "remove", "path": "/spec/syncPolicy"}]],
  ["prepare_apps", ["loop"], "{{ restic_restore_plan }}"],
  ["prepare_apps", ["loop_control", "loop_var"], "restic_restore_app_plan"],
  ["restore_apps", ["loop"], "{{ restic_restore_plan }}"],
  ["restore_apps", ["loop_control", "loop_var"], "restic_restore_app_plan"],
  ["resume_apps", ["loop"], "{{ restic_restore_plan }}"],
  ["resume_apps", ["loop_control", "loop_var"], "restic_restore_app_plan"],
  ["disable_app_sync", ["kubernetes.core.k8s_json_patch", "patch"], [{"op": "remove", "path": "/spec/syncPolicy/automated"}]],
  ["disable_app_sync", ["when"], "restic_restore_app_plan.had_automated_sync | bool"],
  ["scale_down", ["kubernetes.core.k8s_scale", "replicas"], 0],
  ["scale_up", ["kubernetes.core.k8s_scale", "replicas"], "{{ item.replicas }}"],
  ["scale_down", ["loop"], "{{ restic_restore_app_plan.workloads }}"],
  ["scale_down", ["kubernetes.core.k8s_scale", "wait"], true],
  ["scale_down", ["kubernetes.core.k8s_scale", "api_version"], "{{ item.api_version }}"],
  ["scale_down", ["kubernetes.core.k8s_scale", "kind"], "{{ item.kind }}"],
  ["scale_down", ["kubernetes.core.k8s_scale", "namespace"], "{{ item.namespace }}"],
  ["scale_down", ["kubernetes.core.k8s_scale", "name"], "{{ item.name }}"],
  ["scale_up", ["loop"], "{{ restic_restore_app_plan.workloads }}"],
  ["scale_up", ["kubernetes.core.k8s_scale", "wait"], true],
  ["scale_up", ["kubernetes.core.k8s_scale", "api_version"], "{{ item.api_version }}"],
  ["scale_up", ["kubernetes.core.k8s_scale", "kind"], "{{ item.kind }}"],
  ["scale_up", ["kubernetes.core.k8s_scale", "namespace"], "{{ item.namespace }}"],
  ["scale_up", ["kubernetes.core.k8s_scale", "name"], "{{ item.name }}"],
  ["delete_path_guard", ["loop"], "{{ restic_restore_app_plan.restore_paths }}"],
  ["delete_contents", ["loop"], "{{ restic_restore_app_plan.restore_paths }}"],
  ["restore_app_sync", ["kubernetes.core.k8s", "definition", "spec", "syncPolicy"], "{{ restic_restore_app_plan.sync_policy }}"],
  ["restore_app_sync", ["when"], "restic_restore_app_plan.had_sync_policy | bool"],
]

restore_required_order := [
  ["stale_job_delete", "stale_pod_read"],
  ["stale_pod_read", "stale_pod_delete"],
  ["stale_pod_delete", "restore_transaction"],
  ["applicationset_read", "applicationset_guard"],
  ["applicationset_guard", "applicationset_record"],
  ["applicationset_record", "applicationset_pause"],
  ["applicationset_pause", "prepare_apps"],
  ["prepare_apps", "restore_apps"],
  ["restore_apps", "resume_apps"],
  ["resume_apps", "applicationset_restore"],
  ["resume_apps", "applicationset_remove_policy"],
  ["applicationset_restore", "successful_job_delete"],
  ["applicationset_remove_policy", "successful_job_delete"],
  ["disable_app_sync", "scale_down"],
  ["scale_down", "delete_path_guard"],
  ["delete_path_guard", "delete_contents"],
  ["scale_up", "restore_app_sync"],
]

deny contains msg if {
  role_inventory_input
  some pair in restore_required_order
  not role_before(pair[0], pair[1])
  msg := sprintf("Safety order changed: %s before %s", pair)
}

restore_phase_includes := [file |
  some task in role_branch("restore_transaction", "block")
  file := object.get(task, "ansible.builtin.include_tasks", "")
  file in {"execute_prepare_app.yml", "execute_restore_app.yml", "execute_resume_app.yml"}
]

deny contains "Restore phase order changed" if {
  role_inventory_input
  restore_phase_includes != ["execute_prepare_app.yml", "execute_restore_app.yml", "execute_resume_app.yml"]
}

restore_failure_safe if {
  transaction := role_operation("restore_transaction")
  rescue := object.get(transaction, "rescue", [])
  count([task | some task in rescue; object.get(task, "ansible.builtin.fail", null) != null]) == 1
  every task in rescue {
    object.keys(task) - {"name", "ansible.builtin.debug", "ansible.builtin.fail"} == set()
  }
  every task in object.get(transaction, "always", []) {
    object.keys(task) - {"name", "ansible.builtin.debug"} == set()
  }
}

deny contains "Restore failure branches must fail without mutation" if {
  role_inventory_input
  not restore_failure_safe
}

deny contains "ApplicationSet original sync policy must come from the recorded resource" if {
  role_inventory_input
  value := role_field("applicationset_record", ["ansible.builtin.set_fact", "restic_restore_applicationset_original_sync_policy"])
  not contains(value, "restic_restore_applicationset_info")
}

restore_path_guard_safe if {
  rule := role_field("delete_path_guard", ["ansible.builtin.assert", "that"])[0]
  startswith(rule, "item is match('")
  endswith(rule, "')")
  count(split(rule, "'")) == 3
  pattern := split(rule, "'")[1]
  regex.is_valid(pattern)
  regex.match(pattern, "/restore/data/appdata/ns/pvc")
  every path in ["/", "/restore", "/restore/data/appdata/", "/data/appdata/ns/pvc"] {
    not regex.match(pattern, path)
  }
}

deny contains "Restore delete path guard accepts unsafe roots" if {
  role_inventory_input
  not restore_path_guard_safe
}

restore_delete_command_safe if {
  command := role_field("delete_contents", ["kubernetes.core.k8s_exec", "command"])
  startswith(command, "sh -ceu")
  regex.match(`find .* -mindepth 1 -maxdepth 1 -exec rm -rf -- [{][}] [+];`, command)
  contains(command, "mkdir -p")
  not regex.match(`rm -rf --? [^ ]*item`, command)
}

deny contains "Restore deletion must preserve PVC roots" if {
  role_inventory_input
  not restore_delete_command_safe
}

restore_snapshot_command_safe if {
  command := role_field("restore_contents", ["kubernetes.core.k8s_exec", "command"])
  startswith(command, "restic --retry-lock {{ restic_restore_retry_lock }} restore {{ restic_restore_effective_snapshot }}")
  contains(command, "restic_restore_app_plan.pvc_paths")
  contains(command, "--exclude-xattr")
  every selector, variable in {"--host": "restic_restore_snapshot_host", "--tag": "restic_restore_snapshot_tag", "--path": "restic_restore_snapshot_path", "--target": "restic_restore_target_root"} {
    contains(command, sprintf("%s {{ %s }}", [selector, variable]))
    count(split(command, selector)) == 2
  }
}

deny contains "Restore command must retain selected snapshot and planned PVC paths" if {
  role_inventory_input
  not restore_snapshot_command_safe
}
