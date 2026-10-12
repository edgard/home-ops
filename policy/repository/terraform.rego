package main

import rego.v1

cloudflare_limits := [trim_prefix(rule.allowedVersions, "<") |
	some rule in input.renovate.packageRules
	"terraform-provider" in object.get(rule, "matchDatasources", [])
	"cloudflare/cloudflare" in object.get(rule, "matchPackageNames", [])
	startswith(object.get(rule, "allowedVersions", ""), "<")
]

cloudflare_pins := [provider.version |
	some document in input.terraform
	some block in object.get(document, "terraform", [])
	some providers in object.get(block, "required_providers", [])
	some provider in providers
	provider.source == "cloudflare/cloudflare"
]

valid_cloudflare_pin if {
	count(cloudflare_limits) == 1
	count(cloudflare_pins) == 1
	semver.compare(cloudflare_pins[0], cloudflare_limits[0]) < 0
}

deny contains "Cloudflare must be pinned below its Renovate compatibility limit" if not valid_cloudflare_pin

required_wiring := [
	{"kind": "provider", "name": "cloudflare", "attribute": "api_token", "expression": "${var.cloudflare_api_token}"},
	{"kind": "module", "name": "cloudflare", "attribute": "zone_id", "expression": "${sensitive(var.cloudflare_zone_id)}"},
	{"kind": "provider", "name": "tailscale", "attribute": "oauth_client_secret", "expression": "${var.tailscale_client_secret}"},
]

valid_wiring(wiring) if {
	matches := [block |
		some document in input.terraform
		some block in object.get(object.get(document, wiring.kind, {}), wiring.name, [])
		object.get(block, wiring.attribute, null) == wiring.expression
	]
	count(matches) == 1
}

deny contains msg if {
	some wiring in required_wiring
	not valid_wiring(wiring)
	msg := sprintf("Terraform must preserve native %s.%s wiring", [wiring.name, wiring.attribute])
}

deny contains "Terraform must not restore the retired Bitwarden provider" if {
	some document in input.terraform
	contains(json.marshal(document), "bitwarden-secrets")
}
