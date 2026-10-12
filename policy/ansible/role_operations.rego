package main

import rego.v1

# Inventory adaptation retains documents and inherited guards. Policy selects
# operations by modules/resources and relative order, never display names.
role_tasks(source) := object.get(input.documents, source, [])

role_contains(tasks, path, expected) if {
  count(path) > 0
  some task in tasks
  value := object.get(task, path, null)
  value != null
  expected == null
}

role_contains(tasks, path, expected) if {
  count(path) > 0
  some task in tasks
  object.get(task, path, null) == expected
  expected != null
}

role_contains(tasks, path, expected) if {
  path == []
  expected in tasks
}

role_top_operations := {
  "talos_transaction": [{"task": task, "index": index} |
    some index, task in role_tasks("talos/tasks/generate.yml")
    role_contains(object.get(task, ["block"], []), ["ansible.builtin.tempfile"], null)
  ],
  "warmup_transaction": [{"task": task, "index": index} |
    some index, task in role_tasks("platform/tasks/k8tz_warmup.yml")
    role_contains(object.get(task, ["block"], []), ["kubernetes.core.k8s"], null)
  ],
  "restore_transaction": [{"task": task, "index": index} |
    some index, task in role_tasks("restic/tasks/execute.yml")
    role_contains(object.get(task, ["block"], []), ["ansible.builtin.include_tasks"], "execute_prepare_app.yml")
  ],
  "platform_wait": [{"task": task, "index": index} |
    some index, task in role_tasks("platform/tasks/wait_condition.yml")
    object.get(task, ["kubernetes.core.k8s_info"], null) != null
  ],
  "platform_destroy": [{"task": task, "index": index} |
    some index, task in role_tasks("platform/tasks/destroy.yml")
    object.get(task, ["kubernetes.core.k8s"], null) != null
  ],
  "stale_job_delete": [{"task": task, "index": index} |
    some index, task in role_tasks("restic/tasks/execute.yml")
    object.get(task, ["kubernetes.core.k8s", "kind"], null) == "Job"
  ],
  "stale_pod_read": [{"task": task, "index": index} |
    some index, task in role_tasks("restic/tasks/execute.yml")
    object.get(task, ["kubernetes.core.k8s_info", "kind"], null) == "Pod"
  ],
  "stale_pod_delete": [{"task": task, "index": index} |
    some index, task in role_tasks("restic/tasks/execute.yml")
    object.get(task, ["kubernetes.core.k8s", "kind"], null) == "Pod"
  ],
  "disable_app_sync": [{"task": task, "index": index} |
    some index, task in role_tasks("restic/tasks/execute_prepare_app.yml")
    object.get(task, ["kubernetes.core.k8s_json_patch"], null) != null
  ],
  "scale_down": [{"task": task, "index": index} |
    some index, task in role_tasks("restic/tasks/execute_prepare_app.yml")
    object.get(task, ["kubernetes.core.k8s_scale"], null) != null
  ],
  "delete_path_guard": [{"task": task, "index": index} |
    some index, task in role_tasks("restic/tasks/execute_prepare_app.yml")
    object.get(task, ["ansible.builtin.assert"], null) != null
    object.get(task, ["loop"], null) == "{{ restic_restore_app_plan.restore_paths }}"
  ],
  "delete_contents": [{"task": task, "index": index} |
    some index, task in role_tasks("restic/tasks/execute_prepare_app.yml")
    object.get(task, ["kubernetes.core.k8s_exec"], null) != null
  ],
  "restore_contents": [{"task": task, "index": index} |
    some index, task in role_tasks("restic/tasks/execute_restore_app.yml")
    object.get(task, ["kubernetes.core.k8s_exec"], null) != null
  ],
  "scale_up": [{"task": task, "index": index} |
    some index, task in role_tasks("restic/tasks/execute_resume_app.yml")
    object.get(task, ["kubernetes.core.k8s_scale"], null) != null
  ],
  "restore_app_sync": [{"task": task, "index": index} |
    some index, task in role_tasks("restic/tasks/execute_resume_app.yml")
    object.get(task, ["kubernetes.core.k8s", "definition", "kind"], null) == "Application"
  ],
}

role_branch(name, branch) := [task |
  count(role_top_operations[name]) == 1
  some task in object.get(role_top_operations[name][0].task, branch, [])
]

role_nested_operations := {
  "talos_secret_cleanup": [{"task": task, "index": index} |
    some index, task in role_branch("talos_transaction", "always")
    object.get(task, ["ansible.builtin.file", "path"], null) == "{{ talos_generate_secrets_temp.path | default('') }}"
  ],
  "talos_output_cleanup": [{"task": task, "index": index} |
    some index, task in role_branch("talos_transaction", "always")
    object.get(task, ["ansible.builtin.file", "path"], null) == "{{ talos_generate_output.path | default('') }}"
  ],
  "talos_validate_input": [{"task": task, "index": index} |
    some index, task in role_branch("talos_transaction", "block")
    object.get(task, ["ansible.builtin.include_tasks"], null) == "validate_generation.yml"
  ],
  "warmup_create": [{"task": task, "index": index} |
    some index, task in role_branch("warmup_transaction", "block")
    object.get(task, ["kubernetes.core.k8s", "definition", "kind"], null) == "Pod"
  ],
  "warmup_cleanup": [{"task": task, "index": index} |
    some index, task in role_branch("warmup_transaction", "always")
    object.get(task, ["kubernetes.core.k8s", "kind"], null) == "Pod"
  ],
  "applicationset_read": [{"task": task, "index": index} |
    some index, task in role_branch("restore_transaction", "block")
    object.get(task, ["kubernetes.core.k8s_info", "kind"], null) == "ApplicationSet"
  ],
  "applicationset_guard": [{"task": task, "index": index} |
    some index, task in role_branch("restore_transaction", "block")
    role_contains(object.get(task, ["ansible.builtin.assert", "that"], []), [], "restic_restore_applicationset_info.resources | length == 1")
  ],
  "applicationset_record": [{"task": task, "index": index} |
    some index, task in role_branch("restore_transaction", "block")
    object.get(task, ["ansible.builtin.set_fact", "restic_restore_applicationset_original_sync_policy"], null) != null
  ],
  "applicationset_pause": [{"task": task, "index": index} |
    some index, task in role_branch("restore_transaction", "block")
    object.get(task, ["kubernetes.core.k8s", "definition", "spec", "syncPolicy", "applicationsSync"], null) != null
  ],
  "prepare_apps": [{"task": task, "index": index} |
    some index, task in role_branch("restore_transaction", "block")
    object.get(task, ["ansible.builtin.include_tasks"], null) == "execute_prepare_app.yml"
  ],
  "restore_apps": [{"task": task, "index": index} |
    some index, task in role_branch("restore_transaction", "block")
    object.get(task, ["ansible.builtin.include_tasks"], null) == "execute_restore_app.yml"
  ],
  "resume_apps": [{"task": task, "index": index} |
    some index, task in role_branch("restore_transaction", "block")
    object.get(task, ["ansible.builtin.include_tasks"], null) == "execute_resume_app.yml"
  ],
  "applicationset_restore": [{"task": task, "index": index} |
    some index, task in role_branch("restore_transaction", "block")
    object.get(task, ["kubernetes.core.k8s", "definition", "spec", "syncPolicy"], null) == "{{ restic_restore_applicationset_original_sync_policy }}"
  ],
  "applicationset_remove_policy": [{"task": task, "index": index} |
    some index, task in role_branch("restore_transaction", "block")
    object.get(task, ["kubernetes.core.k8s_json_patch", "kind"], null) == "ApplicationSet"
  ],
  "successful_job_delete": [{"task": task, "index": index} |
    some index, task in role_branch("restore_transaction", "block")
    object.get(task, ["kubernetes.core.k8s", "kind"], null) == "Job"
  ],
  "restore_fail": [{"task": task, "index": index} |
    some index, task in role_branch("restore_transaction", "rescue")
    object.get(task, ["ansible.builtin.fail"], null) != null
  ],
}

role_operations := object.union(role_top_operations, role_nested_operations)

role_operation(name) := role_operations[name][0].task if {
  count(role_operations[name]) == 1
}

role_operation_position(name) := role_operations[name][0].index if {
  count(role_operations[name]) == 1
}

role_inventory_input if { input.kind == "ansible-role-inventory" }

deny contains msg if {
  role_inventory_input
  some name, operations in role_operations
  count(operations) != 1
  msg := sprintf("Missing or ambiguous safety operation: %s", [name])
}

role_field(name, path) := object.get(role_operation(name), path, null)

role_before(first, second) if {
  role_operation_position(first) < role_operation_position(second)
}
