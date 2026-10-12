package main

import rego.v1

test_additional_distinct_keyring_provider_is_allowed if {
	third := {"project": "33333333-3333-4333-8333-333333333333", "credentials": {"access_token": "keyring"}}
	expanded := json.patch(fixture, [{"op": "add", "path": "/secrets/providers/third", "value": third}])
	result := deny with input as expanded
	count(result) == 0
}

test_additional_provider_cannot_duplicate_an_owned_project if {
	expanded := json.patch(fixture, [{"op": "add", "path": "/secrets/providers/third", "value": fixture.secrets.providers.operator}])
	result := deny with input as expanded
	count(result) > 0
}

fixture := {
	"secrets": {
		"providers": {"operator": {"project": "e673cff3-d74c-42cf-8e82-b4e0012bb7db", "credentials": {"access_token": "keyring"}}, "applications": {"project": "16848a5f-8d25-4560-af64-b3b5014052e7", "credentials": {"access_token": "keyring"}}},
		"profiles": {"default": {
			"TALOS_SECRETS_YAML": {"required": true, "providers": ["operator"], "ref": {"item": "talos_secrets_yaml"}},
			"ESO_BWS_ACCESS_TOKEN": {"required": true, "providers": ["operator"], "ref": {"item": "eso_bws_access_token"}},
			"TF_VAR_cloudflare_zone_id": {"required": true, "providers": ["operator"], "ref": {"item": "cloudflare_zone_id"}},
			"TF_VAR_tailscale_client_id": {"required": true, "providers": ["operator"], "ref": {"item": "tailscale_oauth_client_id"}},
			"TF_VAR_tailscale_client_secret": {"required": true, "providers": ["applications"], "ref": {"item": "shared-client-secret"}},
		}},
		"scopes": {"cluster": {"secrets": ["TALOS_SECRETS_YAML", "ESO_BWS_ACCESS_TOKEN"]}, "platform": {"secrets": ["ESO_BWS_ACCESS_TOKEN"]}},
	},
	"tailscale_eso_item": "shared-client-secret",
	"terraform": {
		"main.tf": {"terraform": [{"required_providers": [{"cloudflare": {"source": "cloudflare/cloudflare", "version": "5.25.0"}}]}], "provider": {"cloudflare": [{"api_token": "${var.cloudflare_api_token}"}]}, "module": {"cloudflare": [{"zone_id": "${sensitive(var.cloudflare_zone_id)}"}]}},
		"tailscale.tf": {"provider": {"tailscale": [{"oauth_client_secret": "${var.tailscale_client_secret}"}]}},
	},
	"renovate": {"packageRules": [{"matchDatasources": ["terraform-provider"], "matchPackageNames": ["cloudflare/cloudflare"], "allowedVersions": "<5.26.0"}]},
	"tasks": {"secrets:setup": {"cmds": ["ansible-playbook ansible/playbooks/secrets-setup.yml"]}, "secrets:sync-cluster-token": {"cmds": [{"task": "secrets:invoke", "vars": {"playbook": "secrets-sync-cluster-token.yml"}}]}},
	"paths": {"scripts": false, "ansible/roles/talos/files/secrets.vault.yml": false, "ansible/vault/operator.yml": false, "ansible/playbooks/secrets-setup.yml": true, "ansible/playbooks/secrets-sync-cluster-token.yml": true},
	"talos": {"installer_version": "v1.13.1", "patch_image": "factory.talos.dev/metal-installer/fixture:v1.13.1", "kubernetes_version": "v1.36.1"},
	"validation": {"render": [0], "export": [1], "schema": [2, 3], "configuration": [{"ansible.builtin.command": {"argv": ["kubeconform", "-strict"]}}], "helm_templates": [["helm", "template", "--include-crds"]]},
}

test_valid_inventory if {
	result := deny with input as fixture
	count(result) == 0
}

test_reject_shared_or_invalid_project if {
	every project in ["", "not-a-uuid", "e673cff3-d74c-42cf-8e82-b4e0012bb7db"] {
		bad := json.patch(fixture, [{"op": "replace", "path": "/secrets/providers/applications/project", "value": project}])
		result := deny with input as bad
		count(result) > 0
	}
}

test_reject_provider_cache_and_non_keyring if {
	changes := [{"op": "add", "path": "/secrets/providers/operator/cache", "value": true}, {"op": "replace", "path": "/secrets/providers/operator/credentials/access_token", "value": "environment"}]
	every change in changes {
		result := deny with input as json.patch(fixture, [change])
		count(result) > 0
	}
}

test_reject_optional_path_or_ambiguous_secret if {
	changes := [
		{"op": "replace", "path": "/secrets/profiles/default/TALOS_SECRETS_YAML/required", "value": false},
		{"op": "add", "path": "/secrets/profiles/default/TALOS_SECRETS_YAML/as_path", "value": true},
		{"op": "replace", "path": "/secrets/profiles/default/TALOS_SECRETS_YAML/providers", "value": ["operator", "applications"]},
		{"op": "remove", "path": "/secrets/profiles/default/TALOS_SECRETS_YAML/ref"},
	]
	every change in changes {
		result := deny with input as json.patch(fixture, [change])
		count(result) > 0
	}
}

test_reject_changed_scopes_and_secret_ownership if {
	changes := [
		{"op": "replace", "path": "/secrets/scopes/platform/secrets", "value": ["TALOS_SECRETS_YAML"]},
		{"op": "replace", "path": "/tailscale_eso_item", "value": "different-item"},
		{"op": "replace", "path": "/secrets/profiles/default/TF_VAR_cloudflare_zone_id/providers", "value": ["applications"]},
		{"op": "replace", "path": "/secrets/profiles/default/TF_VAR_tailscale_client_id/ref/item", "value": "different-id"},
	]
	every change in changes {
		result := deny with input as json.patch(fixture, [change])
		count(result) > 0
	}
}

test_reject_provider_compatibility_and_legacy_reads if {
	changes := [
		{"op": "replace", "path": "/terraform/main.tf/terraform/0/required_providers/0/cloudflare/version", "value": "5.26.0"},
		{"op": "replace", "path": "/terraform/main.tf/provider/cloudflare/0/api_token", "value": "${data.bitwarden_secret.token.value}"},
		{"op": "add", "path": "/terraform/legacy.tf", "value": {"provider": {"bitwarden-secrets": [{}]}}},
	]
	every change in changes {
		result := deny with input as json.patch(fixture, [change])
		count(result) > 0
	}
}

test_reject_retired_workflows if {
	changes := [
		{"op": "replace", "path": "/paths/scripts", "value": true},
		{"op": "add", "path": "/tasks/tf:migrate-secret-state", "value": {}},
		{"op": "replace", "path": "/tasks/secrets:setup/cmds", "value": ["scripts/setup.sh"]},
		{"op": "replace", "path": "/paths/ansible~1playbooks~1secrets-setup.yml", "value": false},
	]
	every change in changes {
		result := deny with input as json.patch(fixture, [change])
		count(result) > 0
	}
}

test_reject_upgrade_support_or_patch_drift if {
	changes := [
		{"op": "replace", "path": "/talos/installer_version", "value": "v1.14.0"},
		{"op": "replace", "path": "/talos/kubernetes_version", "value": "v1.37.0"},
		{"op": "replace", "path": "/talos/patch_image", "value": "factory.talos.dev/metal-installer/fixture:v1.13.2"},
	]
	every change in changes {
		result := deny with input as json.patch(fixture, [change])
		count(result) > 0
	}
}

test_reject_missing_or_reordered_schema_pipeline if {
	changes := [
		{"op": "replace", "path": "/validation/render", "value": [4]},
		{"op": "replace", "path": "/validation/export", "value": []},
		{"op": "replace", "path": "/validation/helm_templates", "value": [["helm", "template"]]},
		{"op": "replace", "path": "/validation/configuration", "value": [{"ansible.builtin.command": {"argv": ["kubeconform", "-ignore-missing-schemas"]}}]},
	]
	every change in changes {
		result := deny with input as json.patch(fixture, [change])
		count(result) > 0
	}
}

test_reject_missing_required_inventory if {
	every path in ["/secrets/providers", "/secrets/profiles/default", "/secrets/scopes/cluster", "/secrets/profiles/default/TALOS_SECRETS_YAML", "/secrets/profiles/default/TF_VAR_tailscale_client_secret", "/secrets/profiles/default/TF_VAR_tailscale_client_id", "/talos/installer_version", "/talos/kubernetes_version"] {
		result := deny with input as json.patch(fixture, [{"op": "remove", "path": path}])
		count(result) > 0
	}
}

test_reject_empty_required_inventory if {
	every path in ["/secrets/providers", "/secrets/profiles/default"] {
		result := deny with input as json.patch(fixture, [{"op": "replace", "path": path, "value": {}}])
		count(result) > 0
	}
}

test_reject_malformed_upgrade_versions if {
	every path in ["/talos/installer_version", "/talos/kubernetes_version"] {
		every version in ["invalid", "v1.13", ""] {
			result := deny with input as json.patch(fixture, [{"op": "replace", "path": path, "value": version}])
			count(result) > 0
		}
	}
}

test_accept_scope_order_and_harmless_task_names if {
	result := deny with input as json.patch(fixture, [{"op": "replace", "path": "/secrets/scopes/cluster/secrets", "value": ["ESO_BWS_ACCESS_TOKEN", "TALOS_SECRETS_YAML"]}])
	count(result) == 0
}

test_reject_schema_bypass_from_task_block_or_sibling_fact if {
	every config in [
		{"ansible.builtin.set_fact": {"schema_extra_flags": ["-ignore-missing-schemas"]}},
		{"task": {"ansible.builtin.command": {"argv": "{{ ['kubeconform'] + schema_extra_flags }}"}, "vars": {"schema_extra_flags": ["-ignore-missing-schemas"]}}, "parents": []},
		{"task": {"ansible.builtin.command": {"argv": "{{ ['kubeconform'] + schema_extra_flags }}"}}, "parents": [{"vars": {"schema_extra_flags": ["-ignore-missing-schemas"]}}]},
	] {
		result := deny with input as json.patch(fixture, [{"op": "add", "path": "/validation/configuration", "value": [config]}])
		"Missing schemas must fail validation" in result
	}
}
