package main

import rego.v1

valid_provider(provider) if {
	regex.match(`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`, provider.project)
	provider.project != "00000000-0000-0000-0000-000000000000"
	provider.credentials == {"access_token": "keyring"}
	not "cache" in object.keys(provider)
}

valid_providers if {
	{"operator", "applications"} - object.keys(input.secrets.providers) == set()
	every provider in input.secrets.providers { valid_provider(provider) }
	projects := [provider.project | some provider in input.secrets.providers]
	count(projects) == count({project | some project in projects})
}

deny contains "Bitwarden requires distinct valid operator/application projects, Keychain credentials, and no value cache" if not valid_providers

valid_secret(declaration) if {
	declaration.required == true
	count(declaration.providers) == 1
	declaration.providers[0] in object.keys(input.secrets.providers)
	is_string(declaration.ref.item)
	declaration.ref.item != ""
	not "as_path" in object.keys(declaration)
}

deny contains msg if {
	some name, declaration in input.secrets.profiles.default
	not valid_secret(declaration)
	msg := sprintf("Secret %s requires one provider, an item reference, and environment delivery", [name])
}

valid_scope(name, expected) if {
	actual := input.secrets.scopes[name].secrets
	{secret | some secret in actual} == expected
	count(actual) == count(expected)
	every secret in actual { valid_secret(input.secrets.profiles.default[secret]) }
}

deny contains "Cluster and platform SecretSpec scopes must declare exactly their required inputs" if {
	some name, expected in {"cluster": {"TALOS_SECRETS_YAML", "ESO_BWS_ACCESS_TOKEN"}, "platform": {"ESO_BWS_ACCESS_TOKEN"}}
	not valid_scope(name, expected)
}

valid_shared_tailscale if {
	input.secrets.profiles.default.TF_VAR_tailscale_client_secret.providers == ["applications"]
	input.secrets.profiles.default.TF_VAR_tailscale_client_secret.ref.item == input.tailscale_eso_item
}

deny contains "Terraform and ESO must share the existing Tailscale application item" if not valid_shared_tailscale

valid_operator_identifiers if {
	input.secrets.profiles.default.TF_VAR_cloudflare_zone_id.providers == ["operator"]
	input.secrets.profiles.default.TF_VAR_tailscale_client_id.providers == ["operator"]
	input.secrets.profiles.default.TF_VAR_tailscale_client_id.ref.item == "tailscale_oauth_client_id"
}

deny contains "Operator-exclusive infrastructure identifiers must retain their operator project/item" if not valid_operator_identifiers

valid_profile if {
	count(input.secrets.profiles.default) > 0
	every declaration in input.secrets.profiles.default { valid_secret(declaration) }
}

deny contains "SecretSpec requires valid declared environment secrets" if not valid_profile
