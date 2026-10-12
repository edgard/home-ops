package main

import rego.v1

deny contains "Secret orchestration must use role-owned Ansible workflows" if contains(json.marshal(input.tasks), "scripts/")
deny contains "The completed secret-state migration command must stay retired" if "tf:migrate-secret-state" in object.keys(input.tasks)

deny contains msg if {
	some name, entrypoint in {"secrets:setup": "secrets-setup.yml", "secrets:sync-cluster-token": "secrets-sync-cluster-token.yml"}
	not contains(json.marshal(object.get(input.tasks, name, {})), entrypoint)
	msg := sprintf("Task %s must launch its Ansible entry point", [name])
}

deny contains msg if {
	some path in {"scripts", "ansible/vault/operator.yml", "ansible/roles/talos/files/secrets.vault.yml"}
	input.paths[path]
	msg := sprintf("Retired secret workflow must stay absent: %s", [path])
}

deny contains msg if {
	some path in {"ansible/playbooks/secrets-setup.yml", "ansible/playbooks/secrets-sync-cluster-token.yml"}
	not input.paths[path]
	msg := sprintf("Missing operator Ansible entry point: %s", [path])
}
