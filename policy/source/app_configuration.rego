package main

import rego.v1

# This inventory preserves parsed values and owned manifests. These contracts
# describe configuration; Ansible only collects and normalizes the source data.
app_configuration_names := {"karakeep", "radarr", "sonarr", "prowlarr", "qbittorrent", "recyclarr", "jellyfin", "changedetection", "gatus"}

deny contains msg if {
	some app in input.apps
	app.app_name in app_configuration_names
	not app_configuration_valid(app)
	msg := sprintf("%s application configuration contract failed in %s", [app.app_name, app.values_file])
}

app_configuration_valid(app) if {
	app.app_name == "karakeep"
	chrome := object.get(app, ["values", "controllers", "chrome", "containers", "app"], {})
	chrome.image.repository == "ghcr.io/karakeep-app/karakeep-chrome"
	not "command" in object.keys(chrome)
	args := object.get(chrome, "args", [])
	is_array(args)
	every arg in args {
		is_string(arg)
		not arg in {"--no-sandbox", "--disable-software-rasterizer"}
		not startswith(arg, "--remote-debugging-")
	}
	url := object.get(app, ["values", "controllers", "main", "containers", "app", "env", "BROWSER_WEB_URL"], "")
	parts := regex.find_all_string_submatch_n(`^[A-Za-z][A-Za-z0-9+.-]*://(?:[^/?#]*@)?(?:\[[^]]+\]|[^:/?#]+):([0-9]+)(?:[/?#].*)?$`, url, 1)
	to_number(parts[0][1]) == to_number(object.get(app, ["values", "service", "chrome", "ports", "http", "port"], 0))
}

app_configuration_valid(app) if {
	app.app_name in {"radarr", "sonarr", "prowlarr"}
	object.get(app, ["values", "controllers", "main", "containers", "app", "env", "TMPDIR"], "") == "/tmp"
	capabilities := object.get(app, ["values", "controllers", "main", "containers", "app", "securityContext", "capabilities", "add"], null)
	is_array(capabilities)
	not "CHOWN" in capabilities
}

app_configuration_valid(app) if {
	app.app_name == "qbittorrent"
	gluetun := object.get(app, ["values", "controllers", "main", "containers", "gluetun"], {})
	gluetun.probes.readiness.type == "HTTP"
	address := split(gluetun.env.HEALTH_SERVER_ADDRESS, ":")
	port := address[count(address) - 1]
	to_number(port) > 0
	to_number(gluetun.probes.readiness.port) == to_number(port)
	port in split(gluetun.env.FIREWALL_INPUT_PORTS, ",")
}

app_configuration_valid(app) if {
	app.app_name == "recyclarr"
	config := app.embedded_recyclarr
	is_object(config.sonarr)
	is_object(config.radarr)
	every instances in [config.sonarr, config.radarr] {
		every _, instance in instances {
			is_object(instance.custom_format_groups)
			is_array(instance.custom_format_groups.add)
			every group in instance.custom_format_groups.add {
				is_object(group)
				"trash_id" in object.keys(group)
			}
		}
	}
	config.sonarr["web-2160p-v4"].media_naming.series == "jellyfin-tvdb"
	config.radarr["uhd-bluray-web"].media_naming.folder == "jellyfin-tmdb"
	config.radarr["uhd-bluray-web"].media_naming.movie.standard == "jellyfin-tmdb"
}

app_configuration_valid(app) if {
	app.app_name == "jellyfin"
	controller := app.values.controllers.main
	container := controller.containers.app
	container.probes.liveness.spec.tcpSocket.port == "http"
	container.probes.readiness.spec.httpGet.path == "/health"
	networks := json.unmarshal(controller.pod.annotations["k8s.v1.cni.cncf.io/networks"])
	some network in networks
	network.name == "multus-lan-bridge"
	network.namespace == "kube-system"
	"192.168.1.245/24" in network.ips
	container.env.JELLYFIN_PublishedServerUrl == "http://192.168.1.245:8096"
	discovery := [port | some port in container.ports; port.containerPort == 7359; port.protocol == "UDP"]
	count(discovery) == 1
}

app_configuration_valid(app) if {
	app.app_name == "changedetection"
	container := app.values.controllers.main.containers.app
	is_string(container.env.LLM_MODEL)
	trim_space(container.env.LLM_MODEL) != ""
	to_number(container.env.LLM_MAX_INPUT_CHARS) >= 1
	not "LLM_API_BASE" in object.keys(container.env)
	not "LLM_FEATURES_DISABLED" in object.keys(container.env)
	secrets := [doc | some doc in app.documents; doc.kind == "ExternalSecret"; doc.metadata.name == "changedetection-credentials"]
	count(secrets) == 1
	secret := secrets[0]
	secret.spec.secretStoreRef == {"name": "external-secrets-store", "kind": "ClusterSecretStore"}
	some source in container.envFrom
	source.secretRef.name == secret.spec.target.name
	regex.match(`^\{\{\s*\.openai_api_key\s*\}\}$`, secret.spec.target.template.data.LLM_API_KEY)
	refs := [entry | some entry in secret.spec.data; entry.secretKey == "openai_api_key"]
	count(refs) == 1
	refs[0].remoteRef.key == "openai_api_key"
}

app_configuration_valid(app) if {
	app.app_name == "gatus"
	urls := {endpoint.url | some endpoint in app.values.config.endpoints}
	"https://jellyfin.edgard.org/health" in urls
	"https://crosswatch.edgard.org/healthz" in urls
}
