package main

import rego.v1

test_sensitive_task_requires_no_log if {
  sensitive({"community.general.terraform": {}})
}

test_secret_read_requires_no_log if {
  inventory := {"flat": [{"source": "platform/tasks/verify_secret.yml", "task": {"name": "Read target Secret", "kubernetes.core.k8s_info": {"kind": "Secret"}}, "protected": false, "guards": []}], "documents": {}}
  result := deny with input as inventory
  "Sensitive task lost effective no_log: Read target Secret" in result
}

test_resolved_application_credentials_require_no_log if {
  sensitive({"ansible.builtin.uri": {"url_password": "{{ platform_application_values.argocd_repo_password }}"}})
}

test_retained_token_requires_no_log if {
  sensitive({"ansible.builtin.assert": {"that": "platform_previous_token_secret.resources[0].data.token is string"}})
}



test_protected_secret_read_is_allowed if {
  inventory := {"flat": [{"source": "platform/tasks/verify_secret.yml", "task": {"name": "Read target Secret", "kubernetes.core.k8s_info": {"kind": "Secret"}}, "protected": true, "guards": []}], "documents": {}}
  result := deny with input as inventory
  not "Sensitive task lost effective no_log: Read target Secret" in result
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
  inventory := {"flat": [], "documents": {"tofu/tasks/plan.yml": [{"ansible.builtin.assert": {"that": ["tofu_aws_access_key_id | length > 0", "tofu_aws_secret_access_key | length > 0"]}}, {"community.general.terraform": {}, "environment": {"AWS_ACCESS_KEY_ID": "{{ tofu_aws_access_key_id }}", "AWS_SECRET_ACCESS_KEY": "{{ tofu_aws_secret_access_key }}", "BWS_ACCESS_TOKEN": "{{ tofu_bws_access_token }}", "BW_ACCESS_TOKEN": "{{ tofu_bws_access_token }}"}}]}}
  result := deny with input as inventory
  "Terraform plan must require tofu_cloudflare_api_token before its action" in result
}

test_missing_terraform_action_is_denied if {
  inventory := {"flat": [], "documents": {}}
  result := deny with input as inventory
  "Terraform plan must invoke exactly one community.general.terraform action" in result
}

test_missing_terraform_module_is_denied if {
  inventory := {"flat": [], "documents": {"tofu/tasks/plan.yml": [{"ansible.builtin.assert": {"that": []}}, {"ansible.builtin.debug": {"msg": "fixture"}}]}}
  result := deny with input as inventory
  "Terraform plan must invoke exactly one community.general.terraform action" in result
}

test_restore_exec_requires_check_mode_guard if {
  inventory := {"flat": [{"source": "restic/tasks/execute_restore_app.yml", "task": {"kubernetes.core.k8s_exec": {"command": "restic restore latest"}}, "protected": false, "guards": []}], "documents": {}}
  result := deny with input as inventory
  "Restore exec has no check mode guard: restic/tasks/execute_restore_app.yml" in result
}

test_restore_exec_accepts_inherited_check_mode_guard if {
  inventory := {"flat": [{"source": "restic/tasks/execute_prepare_app.yml", "task": {"kubernetes.core.k8s_exec": {"command": "fixture"}}, "protected": false, "guards": [["not ansible_check_mode"]]}], "documents": {}}
  result := deny with input as inventory
  not "Restore exec has no check mode guard: restic/tasks/execute_prepare_app.yml" in result
}

terraform_fixture := [
  {"name": "Renamed assertion", "ansible.builtin.assert": {"that": ["tofu_aws_access_key_id | length > 0", "tofu_aws_secret_access_key | length > 0", "tofu_cloudflare_api_token | length > 0", "tofu_cloudflare_zone_id | length > 0", "tofu_tailscale_client_id | length > 0", "tofu_tailscale_client_secret | length > 0"]}},
  {"name": "Renamed action", "community.general.terraform": {}, "environment": {"AWS_ACCESS_KEY_ID": "{{ tofu_aws_access_key_id }}", "AWS_SECRET_ACCESS_KEY": "{{ tofu_aws_secret_access_key }}", "TF_VAR_cloudflare_api_token": "{{ tofu_cloudflare_api_token }}", "TF_VAR_cloudflare_zone_id": "{{ tofu_cloudflare_zone_id }}", "TF_VAR_tailscale_client_id": "{{ tofu_tailscale_client_id }}", "TF_VAR_tailscale_client_secret": "{{ tofu_tailscale_client_secret }}"}},
]

bitwarden_fixture := {"kubernetes.core.k8s": {"definition": {"kind": "Secret", "metadata": {"name": "bitwarden-credentials", "namespace": "platform-system"}, "stringData": {"token": "{{ platform_bitwarden_access_token }}"}}}}

layout_inventory(tasks, secrets) := {"flat": [], "documents": {"tofu/tasks/plan.yml": tasks, "tofu/tasks/apply.yml": tasks, "platform/tasks/external_secrets.yml": secrets}}

test_harmless_added_and_renamed_tasks_are_allowed if {
  tasks := array.concat([{"ansible.builtin.debug": {"msg": "harmless"}}], terraform_fixture)
  secrets := [{"ansible.builtin.debug": {"msg": "harmless"}}, bitwarden_fixture]
  result := deny with input as layout_inventory(tasks, secrets)
  count(result) == 0
}

test_terraform_assertion_must_precede_action if {
  result := deny with input as layout_inventory([terraform_fixture[1], terraform_fixture[0]], [bitwarden_fixture])
  "Terraform plan must require tofu_cloudflare_api_token before its action" in result
}

test_duplicate_terraform_actions_are_denied if {
  result := deny with input as layout_inventory(array.concat(terraform_fixture, [terraform_fixture[1]]), [bitwarden_fixture])
  "Terraform plan must invoke exactly one community.general.terraform action" in result
}

test_terraform_credential_mapping_mutation_is_denied if {
  mutated := object.union(terraform_fixture[1], {"environment": object.union(terraform_fixture[1].environment, {"TF_VAR_cloudflare_api_token": "wrong-variable"})})
  result := deny with input as layout_inventory([terraform_fixture[0], mutated], [bitwarden_fixture])
  "Terraform plan lost TF_VAR_cloudflare_api_token credential mapping" in result
}

test_bitwarden_missing_and_duplicate_writes_are_denied if {
  every secrets in [[], [bitwarden_fixture, bitwarden_fixture]] {
    result := deny with input as layout_inventory(terraform_fixture, secrets)
    "Bitwarden bootstrap credential mapping changed" in result
  }
}

test_bitwarden_token_mapping_mutation_is_denied if {
  mutated := {"kubernetes.core.k8s": {"definition": {"kind": "Secret", "metadata": {"name": "bitwarden-credentials", "namespace": "platform-system"}, "stringData": {"token": "wrong-variable"}}}}
  result := deny with input as layout_inventory(terraform_fixture, [mutated])
  "Bitwarden bootstrap credential mapping changed" in result
}
