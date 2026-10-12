package main

import rego.v1

cleanup_required_fields := [
  ["talos_transaction", ["no_log"], true],
  ["talos_validate_input", ["ansible.builtin.include_tasks"], "validate_generation.yml"],
  ["talos_secret_cleanup", ["ansible.builtin.file", "state"], "absent"],
  ["talos_secret_cleanup", ["ansible.builtin.file", "path"], "{{ talos_generate_secrets_temp.path | default('') }}"],
  ["talos_secret_cleanup", ["when"], "talos_generate_secrets_temp is defined"],
  ["talos_output_cleanup", ["ansible.builtin.file", "state"], "absent"],
  ["talos_output_cleanup", ["ansible.builtin.file", "path"], "{{ talos_generate_output.path | default('') }}"],
  ["talos_output_cleanup", ["when"], "talos_generate_output is defined"],
  ["warmup_cleanup", ["kubernetes.core.k8s", "state"], "absent"],
  ["warmup_cleanup", ["kubernetes.core.k8s", "wait"], true],
  ["platform_destroy", ["kubernetes.core.k8s", "state"], "absent"],
  ["platform_destroy", ["kubernetes.core.k8s", "wait"], true],
  ["platform_wait", ["kubernetes.core.k8s_info", "wait"], true],
]

cleanup_present_fields := [
  ["platform_wait", ["kubernetes.core.k8s_info", "wait_condition", "type"]],
  ["platform_wait", ["kubernetes.core.k8s_info", "wait_timeout"]],
  ["platform_wait", ["kubernetes.core.k8s_info", "wait_sleep"]],
]

role_absent_fields := [
  ["platform_wait", ["until"]],
  ["platform_wait", ["failed_when"]],
  ["platform_destroy", ["failed_when"]],
  ["successful_job_delete", ["failed_when"]],
]

deny contains msg if {
  role_inventory_input
  some contract in array.concat(cleanup_required_fields, restore_required_fields)
  name := contract[0]
  path := contract[1]
  role_field(name, path) != contract[2]
  msg := sprintf("Safety field changed: %s.%s", [name, concat(".", path)])
}

deny contains msg if {
  role_inventory_input
  some contract in cleanup_present_fields
  role_field(contract[0], contract[1]) == null
  msg := sprintf("Safety field missing: %s.%s", [contract[0], concat(".", contract[1])])
}

deny contains msg if {
  role_inventory_input
  some contract in role_absent_fields
  role_field(contract[0], contract[1]) != null
  msg := sprintf("Safety field must be absent: %s.%s", [contract[0], concat(".", contract[1])])
}

deny contains "Talos generation transaction requires its check mode guard" if {
  role_inventory_input
  transaction := role_operation("talos_transaction")
  not has_check_guard([object.get(transaction, "when", [])])
}

talos_generation_commands := [argv |
  some task in role_branch("talos_transaction", "block")
  argv := object.get(task, ["ansible.builtin.command", "argv"], [])
  "gen" in argv
]

talos_validation_commands := [argv |
  some task in role_branch("talos_transaction", "block")
  argv := object.get(task, ["ansible.builtin.command", "argv"], [])
  "validate" in argv
]

valid_talos_generation_commands if {
  count(talos_generation_commands) == 1
  count(talos_validation_commands) == 1
  array.slice(talos_generation_commands[0], 0, 3) == ["talosctl", "gen", "config"]
  array.slice(talos_validation_commands[0], 0, 2) == ["talosctl", "validate"]
  some index, arg in talos_validation_commands[0]
  arg == "--mode"
  talos_validation_commands[0][index + 1] == "metal"
}

deny contains "Talos generation must generate and validate metal configuration" if {
  role_inventory_input
  not valid_talos_generation_commands
}

valid_warmup_identity(field) if {
  created := role_operation("warmup_create")
  cleanup := role_operation("warmup_cleanup")
  expected := object.get(created, ["kubernetes.core.k8s", "definition", "metadata", field], null)
  actual := object.get(cleanup, ["kubernetes.core.k8s", field], null)
  is_string(expected)
  expected != ""
  actual == expected
}

deny contains "k8tz cleanup must delete the created warmup pod" if {
  role_inventory_input
  not valid_warmup_identity("name")
}

deny contains "k8tz cleanup namespace must match the created warmup pod" if {
  role_inventory_input
  not valid_warmup_identity("namespace")
}

bootstrap_dependency_includes := [file |
  some task in role_tasks("platform/tasks/bootstrap.yml")
  file := object.get(task, "ansible.builtin.include_tasks", object.get(task, "ansible.builtin.import_tasks", ""))
  file in {"install_release_with_manifests.yml", "install_release.yml", "external_secrets.yml", "argocd.yml"}
]

deny contains "Platform bootstrap dependency order changed" if {
  role_inventory_input
  bootstrap_dependency_includes != ["install_release_with_manifests.yml", "install_release.yml", "external_secrets.yml", "argocd.yml"]
}

# Includes and branches inherit failure masking too. A cleanup task cannot
# suppress native deletion failures just by moving ignore_errors to its block.
safety_failure_sources := {
  "talos/tasks/generate.yml", "platform/tasks/k8tz_warmup.yml",
  "platform/tasks/wait_condition.yml", "platform/tasks/destroy.yml",
  "restic/tasks/execute.yml", "restic/tasks/execute_prepare_app.yml",
  "restic/tasks/execute_restore_app.yml", "restic/tasks/execute_resume_app.yml",
}

deny contains msg if {
  some entry in input.flat
  entry.source in safety_failure_sources
  object.get(entry, "failure_masked", false)
  msg := sprintf("Safety operation inherits failure masking: %s", [entry.source])
}
