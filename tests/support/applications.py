"""Application contracts use original metadata, values, and owned resources."""

import ipaddress
import json
import re
from urllib.parse import urlsplit

import yaml

from tests.support.sources import KubernetesLoader

SECTIONS = [
    "defaultPodOptions",
    "controllers",
    "serviceAccount",
    "rbac",
    "service",
    "route",
    "persistence",
    "configMaps",
]


def ordered(keys, expected):
    present = [key for key in keys if key in expected]
    assert present == [key for key in expected if key in keys], "canonical field order"


def assert_application(app):
    metadata, values = app.metadata, app.values
    chart = metadata["chart"]
    assert isinstance(chart["repo"], str) and chart["repo"], (
        f"chart repository: {app.path}"
    )
    assert isinstance(chart["version"], str) and chart["version"], (
        f"chart version: {app.path}"
    )
    assert chart["repo"].startswith("oci://") or chart.get("name"), (
        f"HTTP chart name: {app.path}"
    )
    assert str(metadata["sync"]["wave"]) in {"-4", "-3", "-2", "-1", "0"}, (
        f"sync wave: {app.path}"
    )
    if "ignoreDifferences" in metadata:
        assert isinstance(metadata["ignoreDifferences"], list), "ignoreDifferences list"
        assert all(
            isinstance(entry, dict) and {"group", "kind"} <= entry.keys()
            for entry in metadata["ignoreDifferences"]
        ), "ignoreDifferences group/kind"
    if chart["repo"] == "oci://ghcr.io/argoproj/argo-helm/argo-cd":
        assert not any(doc.get("kind") == "HTTPRoute" for doc in app.documents), (
            "Argo CD route belongs in chart values"
        )
    if chart["repo"] != "oci://ghcr.io/bjw-s-labs/helm/app-template":
        return
    assert re.fullmatch(r"[45]\.[0-9]+\.[0-9]+", chart["version"]), (
        "supported app-template major"
    )
    ordered(values.keys(), SECTIONS)
    for field in ("controllers", "service", "route"):
        if values.get(field):
            assert "main" in values[field], f"primary {field}.main: {app.path}"
    assert (
        values.get("service", {}).get("main", {}).get("controller", "main") == "main"
    ), "service controller"
    route = values.get("route", {}).get("main", {})
    assert all(
        not host or host.endswith(".edgard.org") for host in route.get("hostnames", [])
    ), "route domain"
    assert all(
        ref.get("identifier", "main") in ("", "main")
        for rule in route.get("rules", [])
        for ref in rule.get("backendRefs", [])
    ), "route backend controller"
    security = values.get("defaultPodOptions", {}).get("securityContext", {})
    if security:
        shared = app.category == "media" and any(
            claim.get("existingClaim") == "media"
            for claim in values.get("persistence", {}).values()
        )
        nonroot = {
            "fsGroup": 0 if shared else 1000,
            "fsGroupChangePolicy": "OnRootMismatch",
            "runAsGroup": 1000,
            "runAsNonRoot": True,
            "runAsUser": 1000,
        }
        root = {
            "fsGroup": 0,
            "fsGroupChangePolicy": "OnRootMismatch",
            "runAsGroup": 0,
            "runAsNonRoot": False,
            "runAsUser": 0,
        }
        assert any(
            all(security.get(key) == value for key, value in profile.items())
            for profile in (nonroot, root)
        ), f"pod security profile: {app.path}"


class RecyclarrLoader(KubernetesLoader):
    pass


RecyclarrLoader.add_constructor(
    "!env_var", lambda loader, node: loader.construct_scalar(node)
)


def assert_recyclarr(config):
    for service in ("sonarr", "radarr"):
        assert isinstance(config[service], dict), f"Recyclarr {service} instances"
        for instance in config[service].values():
            groups = instance["custom_format_groups"]
            assert isinstance(groups, dict) and isinstance(groups["add"], list), (
                "Recyclarr format groups"
            )
            assert all(
                isinstance(group, dict) and "trash_id" in group
                for group in groups["add"]
            ), "Recyclarr trash IDs"
    assert config["sonarr"]["web-2160p-v4"]["media_naming"]["series"] == "jellyfin-tvdb"
    naming = config["radarr"]["uhd-bluray-web"]["media_naming"]
    assert naming["folder"] == naming["movie"]["standard"] == "jellyfin-tmdb"


def assert_app_configuration(app):
    name, values = app.name, app.values
    if name == "karakeep":
        chrome = values["controllers"]["chrome"]["containers"]["app"]
        assert (
            chrome["image"]["repository"] == "ghcr.io/karakeep-app/karakeep-chrome"
        ), "managed browser image"
        assert "command" not in chrome, "managed browser entrypoint"
        args = chrome.get("args", [])
        assert isinstance(args, list) and all(
            isinstance(arg, str)
            and arg not in {"--no-sandbox", "--disable-software-rasterizer"}
            and not arg.startswith("--remote-debugging-")
            for arg in args
        ), "managed browser flags"
        url = urlsplit(
            values["controllers"]["main"]["containers"]["app"]["env"]["BROWSER_WEB_URL"]
        )
        assert url.port == int(values["service"]["chrome"]["ports"]["http"]["port"]), (
            "browser service port"
        )
    elif name in {"radarr", "sonarr", "prowlarr"}:
        container = values["controllers"]["main"]["containers"]["app"]
        assert container["env"]["TMPDIR"] == "/tmp", "ARR temporary directory"
        capabilities = container["securityContext"]["capabilities"]["add"]
        assert isinstance(capabilities, list) and "CHOWN" not in capabilities, (
            "ARR ownership safety"
        )
    elif name == "qbittorrent":
        vpn = values["controllers"]["main"]["containers"]["gluetun"]
        port = vpn["env"]["HEALTH_SERVER_ADDRESS"].rsplit(":", 1)[-1]
        assert int(port) > 0 and int(vpn["probes"]["readiness"]["port"]) == int(port), (
            "VPN health port"
        )
        assert vpn["probes"]["readiness"]["type"] == "HTTP" and port in vpn["env"][
            "FIREWALL_INPUT_PORTS"
        ].split(","), "VPN readiness/firewall"
    elif name == "jellyfin":
        controller = values["controllers"]["main"]
        container = controller["containers"]["app"]
        assert container["probes"]["liveness"]["spec"]["tcpSocket"]["port"] == "http"
        assert container["probes"]["readiness"]["spec"]["httpGet"]["path"] == "/health"
        networks = json.loads(
            controller["pod"]["annotations"]["k8s.v1.cni.cncf.io/networks"]
        )
        addresses = [
            str(ipaddress.ip_interface(cidr).ip)
            for network in networks
            if network["name"] == "multus-lan-bridge"
            and network["namespace"] == "kube-system"
            for cidr in network["ips"]
        ]
        published = urlsplit(container["env"]["JELLYFIN_PublishedServerUrl"])
        assert published.hostname in addresses and published.scheme == "http", (
            "published Jellyfin LAN address"
        )
        assert published.port == int(
            values["service"]["main"]["ports"]["http"]["port"]
        ), "published Jellyfin service port"
        assert (
            sum(
                port.get("containerPort") == 7359 and port.get("protocol") == "UDP"
                for port in container["ports"]
            )
            == 1
        ), "Jellyfin UDP discovery"
    elif name == "changedetection":
        container = values["controllers"]["main"]["containers"]["app"]
        env = container["env"]
        assert (
            isinstance(env["LLM_MODEL"], str)
            and env["LLM_MODEL"].strip()
            and float(env["LLM_MAX_INPUT_CHARS"]) >= 1
        ), "LLM inputs"
        assert not {"LLM_API_BASE", "LLM_FEATURES_DISABLED"} & env.keys(), (
            "active LLM configuration"
        )
        secrets = [
            doc
            for doc in app.documents
            if doc.get("kind") == "ExternalSecret"
            and doc["metadata"]["name"] == "changedetection-credentials"
        ]
        assert len(secrets) == 1, "one Changedetection credential"
        secret = secrets[0]["spec"]
        assert secret["secretStoreRef"] == {
            "name": "external-secrets-store",
            "kind": "ClusterSecretStore",
        }
        assert any(
            entry.get("secretRef", {}).get("name") == secret["target"]["name"]
            for entry in container["envFrom"]
        ), "consumed LLM credential"
        assert re.fullmatch(
            r"\{\{\s*\.openai_api_key\s*\}\}",
            secret["target"]["template"]["data"]["LLM_API_KEY"],
        )
        refs = [
            entry for entry in secret["data"] if entry["secretKey"] == "openai_api_key"
        ]
        assert len(refs) == 1 and refs[0]["remoteRef"]["key"] == "openai_api_key", (
            "shared OpenAI item"
        )
    elif name == "recyclarr":
        configs = [
            doc["data"]["recyclarr.yml"]
            for doc in app.documents
            if doc.get("kind") == "ConfigMap"
            and doc["metadata"]["name"] == "recyclarr-config"
        ]
        assert len(configs) == 1, "one Recyclarr configuration"
        assert_recyclarr(yaml.load(configs[0], Loader=RecyclarrLoader))
    elif name == "gatus":
        urls = {endpoint["url"] for endpoint in values["config"]["endpoints"]}
        assert {
            "https://jellyfin.edgard.org/health",
            "https://crosswatch.edgard.org/healthz",
        } <= urls, "application health paths"
