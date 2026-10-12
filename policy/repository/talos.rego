package main

import rego.v1

deny contains "Talos 1.14 requires an installer migration" if semver.compare(trim_prefix(input.talos.installer_version, "v"), "1.14.0") >= 0
deny contains "Kubernetes 1.37 requires upgrading the deployed Talos 1.13 node first" if semver.compare(trim_prefix(input.talos.kubernetes_version, "v"), "1.37.0") >= 0

valid_upgrade_targets if {
	semver.is_valid(trim_prefix(input.talos.installer_version, "v"))
	semver.is_valid(trim_prefix(input.talos.kubernetes_version, "v"))
	is_string(input.talos.patch_image)
	endswith(input.talos.patch_image, concat("", [":", input.talos.installer_version]))
}

deny contains "Talos installer and Kubernetes upgrade targets must be valid and aligned" if not valid_upgrade_targets
