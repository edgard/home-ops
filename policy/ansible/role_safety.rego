package main

import rego.v1

sensitive(task) if {
  regex.match(`\b(tofu_(aws_access_key_id|aws_secret_access_key|cloudflare_api_token|cloudflare_zone_id|tailscale_client_id|tailscale_client_secret)|platform_(bitwarden_access_token|application_values|application_values_result|previous_token_secret|restored_token_secret|secret_target)|talos_(secrets_yaml|generate_secrets_temp|generate_output))\b`, json.marshal(task))
}

sensitive(task) if { object.get(task, "community.general.terraform", null) != null }

sensitive(task) if { object.get(object.get(task, "kubernetes.core.k8s", {}), "definition", {}).kind == "Secret" }

sensitive(task) if { object.get(task, "kubernetes.core.k8s_info", {}).kind == "Secret" }

talos_mutation(task) if {
  some module in {"ansible.builtin.command", "ansible.builtin.shell", "ansible.builtin.copy", "ansible.builtin.file", "ansible.builtin.tempfile", "kubernetes.core.k8s"}
  object.get(task, module, null) != null
}

has_check_guard(guards) if {
  walk(guards, [_, condition])
  condition == "not ansible_check_mode"
}

deny contains msg if {
  some entry in input.flat
  sensitive(entry.task)
  entry.protected != true
  msg := sprintf("Sensitive task lost effective no_log: %s", [object.get(entry.task, "name", entry.source)])
}

deny contains msg if {
  some entry in input.flat
  command := object.get(entry.task, "ansible.builtin.command", object.get(entry.task, "ansible.builtin.shell", null))
  command != null
  contains(json.marshal(command), "kubectl")
  msg := sprintf("Use kubernetes.core in %s", [entry.source])
}

deny contains msg if {
  some entry in input.flat
  startswith(entry.source, "talos/tasks/")
  talos_mutation(entry.task)
  not has_check_guard(entry.guards)
  msg := sprintf("Talos mutation has no check mode guard: %s", [object.get(entry.task, "name", entry.source)])
}

destructive_source := {"platform/tasks/wait_condition.yml", "platform/tasks/destroy.yml", "restic/tasks/execute.yml", "restic/tasks/execute_prepare_app.yml", "restic/tasks/execute_resume_app.yml"}

deny contains msg if {
  some entry in input.flat
  startswith(entry.source, "restic/tasks/")
  object.get(entry.task, "kubernetes.core.k8s_exec", null) != null
  not has_check_guard(entry.guards)
  msg := sprintf("Restore exec has no check mode guard: %s", [entry.source])
}

deny contains msg if {
  some entry in input.flat
  entry.source in destructive_source
  some module in {"kubernetes.core.k8s", "kubernetes.core.k8s_info", "kubernetes.core.k8s_scale"}
  object.get(entry.task, module, null) != null
  object.get(entry.task, "ignore_errors", false) == true
  msg := sprintf("Failure masking in %s", [entry.source])
}

deny contains msg if {
  some entry in input.flat
  entry.source in destructive_source
  some module in {"kubernetes.core.k8s", "kubernetes.core.k8s_info", "kubernetes.core.k8s_scale"}
  object.get(entry.task, module, null) != null
  object.get(entry.task, "failed_when", null) != null
  msg := sprintf("Failure masking in %s", [entry.source])
}

required_credential_check(checks, credential) if {
  some check in checks
  check == sprintf("%s | length > 0", [credential])
}

terraform_operations(action) := [ {"task": task, "index": index} |
  tasks := object.get(input.documents, sprintf("tofu/tasks/%s.yml", [action]), [])
  some index, task in tasks
  object.get(task, "community.general.terraform", null) != null
]

credential_precedes_action(action, credential, operation_index) if {
  tasks := object.get(input.documents, sprintf("tofu/tasks/%s.yml", [action]), [])
  some index, task in tasks
  index < operation_index
  checks := object.get(object.get(task, "ansible.builtin.assert", {}), "that", [])
  required_credential_check(checks, credential)
}

deny contains msg if {
  some action in {"plan", "apply"}
  count(terraform_operations(action)) != 1
  msg := sprintf("Terraform %s must invoke exactly one community.general.terraform action", [action])
}

deny contains msg if {
  some action in {"plan", "apply"}
  some operation in terraform_operations(action)
  required := {"tofu_aws_access_key_id", "tofu_aws_secret_access_key", "tofu_cloudflare_api_token", "tofu_cloudflare_zone_id", "tofu_tailscale_client_id", "tofu_tailscale_client_secret"}
  some credential in required
  not credential_precedes_action(action, credential, operation.index)
  msg := sprintf("Terraform %s must require %s before its action", [action, credential])
}

deny contains msg if {
  some action in {"plan", "apply"}
  some operation in terraform_operations(action)
  env := object.get(operation.task, "environment", {})
  expected := {"AWS_ACCESS_KEY_ID": "tofu_aws_access_key_id", "AWS_SECRET_ACCESS_KEY": "tofu_aws_secret_access_key", "TF_VAR_cloudflare_api_token": "tofu_cloudflare_api_token", "TF_VAR_cloudflare_zone_id": "tofu_cloudflare_zone_id", "TF_VAR_tailscale_client_id": "tofu_tailscale_client_id", "TF_VAR_tailscale_client_secret": "tofu_tailscale_client_secret"}
  some key, variable in expected
  object.get(env, key, "") != sprintf("{{ %s }}", [variable])
  msg := sprintf("Terraform %s lost %s credential mapping", [action, key])
}

bitwarden_writes := [secret |
  some task in object.get(input.documents, "platform/tasks/external_secrets.yml", [])
  secret := object.get(object.get(task, "kubernetes.core.k8s", {}), "definition", {})
  secret.kind == "Secret"
  secret.metadata.name == "bitwarden-credentials"
]

valid_bitwarden_secret if {
  count(bitwarden_writes) == 1
  some secret in bitwarden_writes
  secret.metadata.namespace == "platform-system"
  secret.stringData.token == "{{ platform_bitwarden_access_token }}"
}

deny contains "Bitwarden bootstrap credential mapping changed" if {
  not valid_bitwarden_secret
}

deny contains msg if {
  some action in {"plan", "apply"}
  some operation in terraform_operations(action)
  environment := object.get(operation.task, "environment", {})
  some key in {"BWS_ACCESS_TOKEN", "BW_ACCESS_TOKEN"}
  key in object.keys(environment)
  msg := sprintf("Terraform %s must not receive %s", [action, key])
}
