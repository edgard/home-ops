package main

import rego.v1

test_changedetection_rejects_subcharacter_input_limits if {
	every limit in [0.5, "0.5"] {
		app := json.patch(app_fixture_changedetection, [{"op": "replace", "path": "/values/controllers/main/containers/app/env/LLM_MAX_INPUT_CHARS", "value": limit}])
		results := deny with input as {"apps": [app]}
		count(results) > 0
	}
}

app_fixture_karakeep := {"app_name": "karakeep", "values": {"controllers": {"chrome": {"containers": {"app": {"image": {"repository": "ghcr.io/karakeep-app/karakeep-chrome"}, "args": []}}}, "main": {"containers": {"app": {"env": {"BROWSER_WEB_URL": "http://chrome:9222"}}}}}, "service": {"chrome": {"ports": {"http": {"port": 9222}}}}}, "values_file": "/repo/apps/karakeep/values.yaml"}

test_app_karakeep_accepts_valid if {
	results := deny with input as {"apps": [app_fixture_karakeep]}
	count(results) == 0
}

test_app_karakeep_rejects_browser_image_override if {
	app := json.patch(app_fixture_karakeep, [{"op": "add", "path": "/values/controllers/chrome/containers/app/image/repository", "value": "chrome"}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_karakeep_rejects_entrypoint_override if {
	app := json.patch(app_fixture_karakeep, [{"op": "add", "path": "/values/controllers/chrome/containers/app/command", "value": ["chrome"]}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_karakeep_rejects_sandbox_disabled if {
	app := json.patch(app_fixture_karakeep, [{"op": "add", "path": "/values/controllers/chrome/containers/app/args", "value": ["--no-sandbox"]}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_karakeep_rejects_rasterizer_disabled if {
	app := json.patch(app_fixture_karakeep, [{"op": "add", "path": "/values/controllers/chrome/containers/app/args", "value": ["--disable-software-rasterizer"]}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_karakeep_rejects_debugging_override if {
	app := json.patch(app_fixture_karakeep, [{"op": "add", "path": "/values/controllers/chrome/containers/app/args", "value": ["--remote-debugging-port=1234"]}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_karakeep_rejects_browser_service_port_mismatch if {
	app := json.patch(app_fixture_karakeep, [{"op": "add", "path": "/values/controllers/main/containers/app/env/BROWSER_WEB_URL", "value": "http://chrome:9333"}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_karakeep_rejects_missing_structure if {
	app := json.patch(app_fixture_karakeep, [{"op": "add", "path": "/values", "value": {}}, {"op": "add", "path": "/documents", "value": []}, {"op": "add", "path": "/embedded_recyclarr", "value": {}}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_karakeep_rejects_malformed_structure if {
	app := object.union(app_fixture_karakeep, {"values": null, "documents": null, "embedded_recyclarr": null})
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

app_fixture_arr := {"app_name": "radarr", "values": {"controllers": {"main": {"containers": {"app": {"env": {"TMPDIR": "/tmp"}, "securityContext": {"capabilities": {"add": ["SETUID", "SETGID"]}}}}}}}, "values_file": "/repo/apps/arr/values.yaml"}

test_app_arr_accepts_valid if {
	results := deny with input as {"apps": [app_fixture_arr]}
	count(results) == 0
}

test_app_arr_rejects_unsafe_tmpdir if {
	app := json.patch(app_fixture_arr, [{"op": "add", "path": "/values/controllers/main/containers/app/env/TMPDIR", "value": "/config"}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_arr_rejects_chown_capability if {
	app := json.patch(app_fixture_arr, [{"op": "add", "path": "/values/controllers/main/containers/app/securityContext/capabilities/add", "value": ["CHOWN"]}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_arr_rejects_missing_structure if {
	app := json.patch(app_fixture_arr, [{"op": "add", "path": "/values", "value": {}}, {"op": "add", "path": "/documents", "value": []}, {"op": "add", "path": "/embedded_recyclarr", "value": {}}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_arr_rejects_malformed_structure if {
	app := object.union(app_fixture_arr, {"values": null, "documents": null, "embedded_recyclarr": null})
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

app_fixture_qbittorrent := {"app_name": "qbittorrent", "values": {"controllers": {"main": {"containers": {"gluetun": {"env": {"HEALTH_SERVER_ADDRESS": ":9999", "FIREWALL_INPUT_PORTS": "8080,9999"}, "probes": {"readiness": {"type": "HTTP", "port": 9999}}}}}}}, "values_file": "/repo/apps/qbittorrent/values.yaml"}

test_app_qbittorrent_accepts_valid if {
	results := deny with input as {"apps": [app_fixture_qbittorrent]}
	count(results) == 0
}

test_app_qbittorrent_rejects_non_http_readiness if {
	app := json.patch(app_fixture_qbittorrent, [{"op": "add", "path": "/values/controllers/main/containers/gluetun/probes/readiness/type", "value": "TCP"}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_qbittorrent_rejects_readiness_port_mismatch if {
	app := json.patch(app_fixture_qbittorrent, [{"op": "add", "path": "/values/controllers/main/containers/gluetun/probes/readiness/port", "value": 8080}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_qbittorrent_rejects_blocked_health_port if {
	app := json.patch(app_fixture_qbittorrent, [{"op": "add", "path": "/values/controllers/main/containers/gluetun/env/FIREWALL_INPUT_PORTS", "value": "8080"}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_qbittorrent_rejects_missing_structure if {
	app := json.patch(app_fixture_qbittorrent, [{"op": "add", "path": "/values", "value": {}}, {"op": "add", "path": "/documents", "value": []}, {"op": "add", "path": "/embedded_recyclarr", "value": {}}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_qbittorrent_rejects_malformed_structure if {
	app := object.union(app_fixture_qbittorrent, {"values": null, "documents": null, "embedded_recyclarr": null})
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

app_fixture_jellyfin := {"app_name": "jellyfin", "values": {"controllers": {"main": {"pod": {"annotations": {"k8s.v1.cni.cncf.io/networks": "[{\"name\":\"multus-lan-bridge\",\"namespace\":\"kube-system\",\"ips\":[\"192.168.1.245/24\"]}]"}}, "containers": {"app": {"env": {"JELLYFIN_PublishedServerUrl": "http://192.168.1.245:8096"}, "ports": [{"containerPort": 7359, "protocol": "UDP"}], "probes": {"liveness": {"spec": {"tcpSocket": {"port": "http"}}}, "readiness": {"spec": {"httpGet": {"path": "/health"}}}}}}}}}, "values_file": "/repo/apps/jellyfin/values.yaml"}

test_app_jellyfin_accepts_valid if {
	results := deny with input as {"apps": [app_fixture_jellyfin]}
	count(results) == 0
}

test_app_jellyfin_rejects_wrong_liveness_port if {
	app := json.patch(app_fixture_jellyfin, [{"op": "add", "path": "/values/controllers/main/containers/app/probes/liveness/spec/tcpSocket/port", "value": "wrong"}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_jellyfin_rejects_wrong_health_path if {
	app := json.patch(app_fixture_jellyfin, [{"op": "add", "path": "/values/controllers/main/containers/app/probes/readiness/spec/httpGet/path", "value": "/"}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_jellyfin_rejects_missing_lan_address if {
	app := json.patch(app_fixture_jellyfin, [{"op": "add", "path": "/values/controllers/main/pod/annotations/k8s.v1.cni.cncf.io~1networks", "value": "[]"}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_jellyfin_rejects_wrong_published_address if {
	app := json.patch(app_fixture_jellyfin, [{"op": "add", "path": "/values/controllers/main/containers/app/env/JELLYFIN_PublishedServerUrl", "value": "http://wrong:8096"}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_jellyfin_rejects_missing_udp_discovery if {
	app := json.patch(app_fixture_jellyfin, [{"op": "add", "path": "/values/controllers/main/containers/app/ports", "value": []}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_jellyfin_rejects_missing_structure if {
	app := json.patch(app_fixture_jellyfin, [{"op": "add", "path": "/values", "value": {}}, {"op": "add", "path": "/documents", "value": []}, {"op": "add", "path": "/embedded_recyclarr", "value": {}}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_jellyfin_rejects_malformed_structure if {
	app := object.union(app_fixture_jellyfin, {"values": null, "documents": null, "embedded_recyclarr": null})
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

app_fixture_changedetection := {"app_name": "changedetection", "values": {"controllers": {"main": {"containers": {"app": {"env": {"LLM_MODEL": "openai/gpt-5-mini", "LLM_MAX_INPUT_CHARS": 10000}, "envFrom": [{"secretRef": {"name": "changedetection-credentials"}}]}}}}}, "values_file": "/repo/apps/changedetection/values.yaml", "documents": [{"kind": "ExternalSecret", "metadata": {"name": "changedetection-credentials"}, "spec": {"target": {"name": "changedetection-credentials", "template": {"data": {"LLM_API_KEY": "{{ .openai_api_key }}"}}}, "secretStoreRef": {"name": "external-secrets-store", "kind": "ClusterSecretStore"}, "data": [{"secretKey": "openai_api_key", "remoteRef": {"key": "openai_api_key"}}]}}]}

test_app_changedetection_accepts_valid if {
	results := deny with input as {"apps": [app_fixture_changedetection]}
	count(results) == 0
}

test_app_changedetection_rejects_empty_model if {
	app := json.patch(app_fixture_changedetection, [{"op": "add", "path": "/values/controllers/main/containers/app/env/LLM_MODEL", "value": " "}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_changedetection_rejects_nonpositive_input_limit if {
	app := json.patch(app_fixture_changedetection, [{"op": "add", "path": "/values/controllers/main/containers/app/env/LLM_MAX_INPUT_CHARS", "value": 0}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_changedetection_rejects_legacy_api_base if {
	app := json.patch(app_fixture_changedetection, [{"op": "add", "path": "/values/controllers/main/containers/app/env/LLM_API_BASE", "value": "legacy"}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_changedetection_rejects_disabled_llm_features if {
	app := json.patch(app_fixture_changedetection, [{"op": "add", "path": "/values/controllers/main/containers/app/env/LLM_FEATURES_DISABLED", "value": false}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_changedetection_rejects_missing_secret_consumption if {
	app := json.patch(app_fixture_changedetection, [{"op": "add", "path": "/values/controllers/main/containers/app/envFrom", "value": []}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_changedetection_rejects_wrong_secret_store if {
	app := json.patch(app_fixture_changedetection, [{"op": "add", "path": "/documents/0/spec/secretStoreRef/name", "value": "wrong"}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_changedetection_rejects_wrong_api_key_template if {
	app := json.patch(app_fixture_changedetection, [{"op": "add", "path": "/documents/0/spec/target/template/data/LLM_API_KEY", "value": "wrong"}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_changedetection_rejects_wrong_shared_item if {
	app := json.patch(app_fixture_changedetection, [{"op": "add", "path": "/documents/0/spec/data/0/remoteRef/key", "value": "wrong"}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_changedetection_rejects_missing_structure if {
	app := json.patch(app_fixture_changedetection, [{"op": "add", "path": "/values", "value": {}}, {"op": "add", "path": "/documents", "value": []}, {"op": "add", "path": "/embedded_recyclarr", "value": {}}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_changedetection_rejects_malformed_structure if {
	app := object.union(app_fixture_changedetection, {"values": null, "documents": null, "embedded_recyclarr": null})
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

app_fixture_gatus := {"app_name": "gatus", "values": {"config": {"endpoints": [{"url": "https://jellyfin.edgard.org/health"}, {"url": "https://crosswatch.edgard.org/healthz"}]}}, "values_file": "/repo/apps/gatus/values.yaml"}

test_app_gatus_accepts_valid if {
	results := deny with input as {"apps": [app_fixture_gatus]}
	count(results) == 0
}

test_app_gatus_rejects_missing_health_targets if {
	app := json.patch(app_fixture_gatus, [{"op": "add", "path": "/values/config/endpoints", "value": []}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_gatus_rejects_missing_structure if {
	app := json.patch(app_fixture_gatus, [{"op": "add", "path": "/values", "value": {}}, {"op": "add", "path": "/documents", "value": []}, {"op": "add", "path": "/embedded_recyclarr", "value": {}}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_gatus_rejects_malformed_structure if {
	app := object.union(app_fixture_gatus, {"values": null, "documents": null, "embedded_recyclarr": null})
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

app_fixture_recyclarr := {"app_name": "recyclarr", "values_file": "/repo/apps/recyclarr/values.yaml", "embedded_recyclarr": {"sonarr": {"web-2160p-v4": {"custom_format_groups": {"add": [{"trash_id": "id"}]}, "media_naming": {"series": "jellyfin-tvdb"}}}, "radarr": {"uhd-bluray-web": {"custom_format_groups": {"add": [{"trash_id": "id"}]}, "media_naming": {"folder": "jellyfin-tmdb", "movie": {"standard": "jellyfin-tmdb"}}}}}}

test_app_recyclarr_accepts_valid if {
	results := deny with input as {"apps": [app_fixture_recyclarr]}
	count(results) == 0
}

test_app_recyclarr_rejects_nonmapping_format_groups if {
	app := json.patch(app_fixture_recyclarr, [{"op": "add", "path": "/embedded_recyclarr/sonarr/web-2160p-v4/custom_format_groups", "value": []}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_recyclarr_rejects_nonlist_group_additions if {
	app := json.patch(app_fixture_recyclarr, [{"op": "add", "path": "/embedded_recyclarr/sonarr/web-2160p-v4/custom_format_groups/add", "value": "bad"}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_recyclarr_rejects_missing_trash_id if {
	app := json.patch(app_fixture_recyclarr, [{"op": "add", "path": "/embedded_recyclarr/sonarr/web-2160p-v4/custom_format_groups/add", "value": [{}]}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_recyclarr_rejects_incompatible_series_naming if {
	app := json.patch(app_fixture_recyclarr, [{"op": "add", "path": "/embedded_recyclarr/sonarr/web-2160p-v4/media_naming/series", "value": "default"}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_recyclarr_rejects_incompatible_folder_naming if {
	app := json.patch(app_fixture_recyclarr, [{"op": "add", "path": "/embedded_recyclarr/radarr/uhd-bluray-web/media_naming/folder", "value": "default"}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_recyclarr_rejects_incompatible_movie_naming if {
	app := json.patch(app_fixture_recyclarr, [{"op": "add", "path": "/embedded_recyclarr/radarr/uhd-bluray-web/media_naming/movie/standard", "value": "default"}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_recyclarr_rejects_missing_structure if {
	app := json.patch(app_fixture_recyclarr, [{"op": "add", "path": "/values", "value": {}}, {"op": "add", "path": "/documents", "value": []}, {"op": "add", "path": "/embedded_recyclarr", "value": {}}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_app_recyclarr_rejects_malformed_structure if {
	app := object.union(app_fixture_recyclarr, {"values": null, "documents": null, "embedded_recyclarr": null})
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_changedetection_rejects_malformed_duplicate_credential if {
	app := json.patch(app_fixture_changedetection, [{"op": "add", "path": "/documents/0/spec/data/-", "value": {"secretKey": "openai_api_key"}}])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_all_arr_apps_require_safe_tmpdir if {
	every name in ["radarr", "sonarr", "prowlarr"] {
		app := json.patch(app_fixture_arr, [{"op": "replace", "path": "/app_name", "value": name}, {"op": "remove", "path": "/values/controllers/main/containers/app/env/TMPDIR"}])
		results := deny with input as {"apps": [app]}
		count(results) > 0
	}
}

test_gatus_requires_both_special_health_paths if {
	every url in ["https://jellyfin.edgard.org/health", "https://crosswatch.edgard.org/healthz"] {
		app := json.patch(app_fixture_gatus, [{"op": "replace", "path": "/values/config/endpoints", "value": [{"url": url}]}])
		results := deny with input as {"apps": [app]}
		count(results) > 0
	}
}

test_karakeep_allows_omitted_optional_args if {
	app := json.patch(app_fixture_karakeep, [{"op": "remove", "path": "/values/controllers/chrome/containers/app/args"}])
	results := deny with input as {"apps": [app]}
	count(results) == 0
}

test_recyclarr_checks_colliding_instance_names_in_both_services if {
	app := json.patch(app_fixture_recyclarr, [
		{"op": "add", "path": "/embedded_recyclarr/sonarr/duplicate", "value": {"custom_format_groups": {"add": [{}]}}},
		{"op": "add", "path": "/embedded_recyclarr/radarr/duplicate", "value": {"custom_format_groups": {"add": [{"trash_id": "id"}]}}},
	])
	results := deny with input as {"apps": [app]}
	count(results) > 0
}

test_karakeep_accepts_ipv6_browser_url if {
	app := json.patch(app_fixture_karakeep, [{"op": "replace", "path": "/values/controllers/main/containers/app/env/BROWSER_WEB_URL", "value": "http://[fd00::1]:9222/"}])
	results := deny with input as {"apps": [app]}
	count(results) == 0
}
