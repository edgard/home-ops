package main

import rego.v1

valid_schema_pipeline if {
	is_array(input.validation.configuration)
	count(input.validation.render) == 1
	count(input.validation.export) == 1
	count(input.validation.schema) >= 2
	input.validation.render[0] < input.validation.export[0]
	every position in input.validation.schema { position > input.validation.export[0] }
}

deny contains "Render charts before exporting CRDs and validating raw/rendered schemas" if not valid_schema_pipeline
deny contains "Chart rendering must retain the Helm CRDs" if count(input.validation.helm_templates) == 0

deny contains "Chart rendering must retain the Helm CRDs" if {
	some command in input.validation.helm_templates
	not "--include-crds" in command
}

deny contains "Missing schemas must fail validation" if {
	contains(json.marshal(input.validation.configuration), "ignore-missing-schemas")
}
