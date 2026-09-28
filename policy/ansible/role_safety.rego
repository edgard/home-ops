package main

import rego.v1

sensitive(task) if {
  regex.match(`\b(tofu_(aws_access_key_id|aws_secret_access_key|bws_access_token)|platform_bitwarden_access_token|talos_(secrets_file|generate_secrets_temp|generate_output))\b`, json.marshal(task))
}

sensitive(task) if { object.get(task, "community.general.terraform", null) != null }

sensitive(task) if { object.get(object.get(task, "kubernetes.core.k8s", {}), "definition", {}).kind == "Secret" }

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

deny contains msg if {
  some action in {"plan", "apply"}
  tasks := object.get(input.documents, sprintf("tofu/tasks/%s.yml", [action]), [])
  count(tasks) != 2
  msg := sprintf("Terraform %s must define a credential assertion and Terraform action", [action])
}

deny contains msg if {
  some action in {"plan", "apply"}
  tasks := object.get(input.documents, sprintf("tofu/tasks/%s.yml", [action]), [])
  count(tasks) >= 2
  object.get(tasks[1], "community.general.terraform", null) == null
  msg := sprintf("Terraform %s must invoke community.general.terraform", [action])
}

deny contains msg if {
  some action in {"plan", "apply"}
  tasks := input.documents[sprintf("tofu/tasks/%s.yml", [action])]
  checks := object.get(object.get(tasks[0], "ansible.builtin.assert", {}), "that", [])
  required := {"tofu_aws_access_key_id", "tofu_aws_secret_access_key", "tofu_bws_access_token"}
  some credential in required
  not required_credential_check(checks, credential)
  msg := sprintf("Terraform %s must require %s", [action, credential])
}

deny contains msg if {
  some action in {"plan", "apply"}
  tasks := input.documents[sprintf("tofu/tasks/%s.yml", [action])]
  env := object.get(tasks[1], "environment", {})
  expected := {"AWS_ACCESS_KEY_ID": "tofu_aws_access_key_id", "AWS_SECRET_ACCESS_KEY": "tofu_aws_secret_access_key", "BWS_ACCESS_TOKEN": "tofu_bws_access_token", "BW_ACCESS_TOKEN": "tofu_bws_access_token"}
  some key, variable in expected
  object.get(env, key, "") != sprintf("{{ %s }}", [variable])
  msg := sprintf("Terraform %s lost %s credential mapping", [action, key])
}

valid_bitwarden_secret if {
  secret := input.documents["platform/tasks/external_secrets.yml"][0]["kubernetes.core.k8s"].definition
  secret.kind == "Secret"
  secret.metadata.name == "bitwarden-credentials"
  secret.metadata.namespace == "platform-system"
  secret.stringData.token == "{{ platform_bitwarden_access_token }}"
}

deny contains "Bitwarden bootstrap credential mapping changed" if {
  not valid_bitwarden_secret
}
