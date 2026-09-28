package main

import rego.v1

test_sensitive_task_requires_no_log if {
  sensitive({"community.general.terraform": {}})
}

test_talos_check_guard_rejects_weakened_guard if {
  not has_check_guard(["ansible_check_mode or true"])
}

test_talos_check_guard_accepts_inherited_guard if {
  has_check_guard([["not ansible_check_mode"]])
}

test_missing_no_log_is_denied if {
  inventory := {"flat": [{"source": "tofu/tasks/plan.yml", "task": {"name": "Plan", "community.general.terraform": {}}, "protected": false, "guards": []}], "documents": {}}
  result := deny with input as inventory
  "Sensitive task lost effective no_log: Plan" in result
}

test_missing_talos_check_guard_is_denied if {
  inventory := {"flat": [{"source": "talos/tasks/apply.yml", "task": {"name": "Apply", "ansible.builtin.command": {"argv": ["talosctl"]}}, "protected": false, "guards": []}], "documents": {}}
  result := deny with input as inventory
  "Talos mutation has no check mode guard: Apply" in result
}

test_missing_terraform_credential_is_denied if {
  inventory := {"flat": [], "documents": {"tofu/tasks/plan.yml": [{"ansible.builtin.assert": {"that": ["tofu_aws_access_key_id | length > 0", "tofu_aws_secret_access_key | length > 0"]}}, {"environment": {"AWS_ACCESS_KEY_ID": "{{ tofu_aws_access_key_id }}", "AWS_SECRET_ACCESS_KEY": "{{ tofu_aws_secret_access_key }}", "BWS_ACCESS_TOKEN": "{{ tofu_bws_access_token }}", "BW_ACCESS_TOKEN": "{{ tofu_bws_access_token }}"}}]}}
  result := deny with input as inventory
  "Terraform plan must require tofu_bws_access_token" in result
}
