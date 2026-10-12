import copy
from dataclasses import replace

import pytest

from tests.support.applications import assert_application, assert_app_configuration
from tests.support.sources import applications
from tests.support.runtime import ROOT

APPS = applications(ROOT)


@pytest.mark.parametrize("app", APPS, ids=lambda app: f"{app.category}/{app.name}")
def test_application_sources(app):
    assert_application(app)
    assert_app_configuration(app)


@pytest.mark.parametrize(
    "field,value",
    [
        ("chart", {}),
        ("sync", {}),
        ("sync", {"wave": 1}),
        ("ignoreDifferences", {}),
        ("ignoreDifferences", [{}]),
    ],
)
def test_invalid_metadata_rejected(field, value):
    app = next(app for app in APPS if app.name == "karakeep")
    metadata = copy.deepcopy(app.metadata)
    metadata[field] = value
    with pytest.raises((AssertionError, KeyError)):
        assert_application(replace(app, metadata=metadata))


@pytest.mark.parametrize(
    "name",
    [
        "karakeep",
        "radarr",
        "sonarr",
        "prowlarr",
        "qbittorrent",
        "jellyfin",
        "changedetection",
        "gatus",
    ],
)
@pytest.mark.parametrize("values", [{}, None, []])
def test_required_application_structure_cannot_disappear(name, values):
    app = next(app for app in APPS if app.name == name)
    with pytest.raises((AssertionError, KeyError, TypeError)):
        assert_app_configuration(replace(app, values=values))


@pytest.mark.parametrize(
    "name,path,value",
    [
        ("karakeep", "/controllers/chrome/containers/app/image/repository", "browserless/chrome"),
        ("karakeep", "/controllers/chrome/containers/app/command", ["chromium"]),
        ("karakeep", "/controllers/chrome/containers/app/args", ["--no-sandbox"]),
        ("karakeep", "/controllers/chrome/containers/app/args", ["--remote-debugging-port=9222"]),
        ("karakeep", "/controllers/chrome/containers/app/args", "--no-sandbox"),
        ("karakeep", "/controllers/main/containers/app/env/BROWSER_WEB_URL", "http://chrome:9999"),
        ("radarr", "/controllers/main/containers/app/env/TMPDIR", "/root"),
        ("sonarr", "/controllers/main/containers/app/securityContext/capabilities/add", ["CHOWN"]),
        ("prowlarr", "/controllers/main/containers/app/securityContext/capabilities/add", None),
        ("qbittorrent", "/controllers/main/containers/gluetun/probes/readiness/type", "TCP"),
        ("qbittorrent", "/controllers/main/containers/gluetun/probes/readiness/port", 1234),
        ("qbittorrent", "/controllers/main/containers/gluetun/env/FIREWALL_INPUT_PORTS", "1234"),
        ("jellyfin", "/controllers/main/containers/app/probes/readiness/spec/httpGet/path", "/"),
        (
            "jellyfin",
            "/controllers/main/containers/app/env/JELLYFIN_PublishedServerUrl",
            "http://192.0.2.1:8096",
        ),
        ("jellyfin", "/controllers/main/containers/app/ports", []),
        ("changedetection", "/controllers/main/containers/app/env/LLM_MODEL", ""),
        ("changedetection", "/controllers/main/containers/app/env/LLM_MAX_INPUT_CHARS", 0),
        ("changedetection", "/controllers/main/containers/app/env/LLM_API_BASE", "synthetic"),
        ("changedetection", "/controllers/main/containers/app/env/LLM_FEATURES_DISABLED", True),
        ("changedetection", "/controllers/main/containers/app/envFrom", []),
        ("gatus", "/config/endpoints", []),
    ],
)
def test_app_specific_configuration_regressions(name, path, value):
    import dataclasses
    import jsonpatch

    app = next(app for app in APPS if app.name == name)
    bad = dataclasses.replace(
        app, values=jsonpatch.apply_patch(app.values, [{"op": "add", "path": path, "value": value}])
    )
    with pytest.raises((AssertionError, KeyError, TypeError, ValueError)):
        assert_app_configuration(bad)


def test_changedetection_credential_and_safe_embedded_recyclarr():
    import copy
    import dataclasses
    import yaml
    from tests.support.applications import RecyclarrLoader, assert_recyclarr

    app = next(app for app in APPS if app.name == "changedetection")
    with pytest.raises(AssertionError):
        assert_app_configuration(dataclasses.replace(app, documents=[]))
    documents = copy.deepcopy(app.documents)
    next(
        entry
        for doc in documents
        if doc["kind"] == "ExternalSecret"
        for entry in doc["spec"]["data"]
        if entry["secretKey"] == "openai_api_key"
    )["remoteRef"]["key"] = "other-item"
    with pytest.raises(AssertionError):
        assert_app_configuration(dataclasses.replace(app, documents=documents))
    app = next(app for app in APPS if app.name == "recyclarr")
    config = yaml.load(app.documents[0]["data"]["recyclarr.yml"], Loader=RecyclarrLoader)
    assert_recyclarr(config)
    assert isinstance(config["sonarr"]["web-2160p-v4"]["api_key"], str)
    for content in ["sonarr: []\nradarr: {}", "sonarr: [", "!!python/object:os.system {}"]:
        with pytest.raises((AssertionError, KeyError, yaml.YAMLError)):
            assert_recyclarr(yaml.load(content, Loader=RecyclarrLoader))


@pytest.mark.parametrize("version", ["4.99.0", "5.0.0", "3.0.0", "6.0.0", "bad", ""])
def test_supported_chart_majors_and_optional_sections(version):
    import dataclasses
    import copy

    app = next(
        app
        for app in APPS
        if app.metadata["chart"]["repo"] == "oci://ghcr.io/bjw-s-labs/helm/app-template"
    )
    metadata = copy.deepcopy(app.metadata)
    metadata["chart"]["version"] = version
    fixture = dataclasses.replace(app, metadata=metadata, values={"controllers": {"main": {}}})
    if version.startswith(("4.", "5.")):
        assert_application(fixture)
        with pytest.raises(AssertionError):
            assert_application(dataclasses.replace(fixture, values={"controllers": {"other": {}}}))
        with pytest.raises(AssertionError):
            assert_application(
                dataclasses.replace(fixture, values={"route": {}, "controllers": {"main": {}}})
            )
    else:
        with pytest.raises(AssertionError):
            assert_application(fixture)


@pytest.mark.parametrize(
    "category,group,valid",
    [
        ("media", 0, True),
        ("media", 1000, False),
        ("selfhosted", 0, False),
        ("selfhosted", 1000, True),
    ],
)
def test_shared_media_security_profile(category, group, valid):
    import dataclasses
    from pathlib import Path

    app = next(
        app
        for app in APPS
        if app.metadata["chart"]["repo"] == "oci://ghcr.io/bjw-s-labs/helm/app-template"
    )
    fixture = dataclasses.replace(
        app,
        path=Path("apps") / category / "demo",
        values={
            "defaultPodOptions": {
                "securityContext": {
                    "fsGroup": group,
                    "fsGroupChangePolicy": "OnRootMismatch",
                    "runAsGroup": 1000,
                    "runAsNonRoot": True,
                    "runAsUser": 1000,
                }
            },
            "persistence": {"data": {"existingClaim": "media"}},
        },
    )
    if valid:
        assert_application(fixture)
    else:
        with pytest.raises(AssertionError):
            assert_application(fixture)


def test_argocd_route_ownership_and_browser_ipv6():
    import dataclasses
    import copy

    app = next(app for app in APPS if app.name == "argocd")
    with pytest.raises(AssertionError):
        assert_application(dataclasses.replace(app, documents=[{"kind": "HTTPRoute"}]))
    app = next(app for app in APPS if app.name == "karakeep")
    values = copy.deepcopy(app.values)
    chrome = values["controllers"]["chrome"]["containers"]["app"]
    chrome.pop("args", None)
    values["controllers"]["main"]["containers"]["app"]["env"]["BROWSER_WEB_URL"] = (
        "http://[::1]:" + str(values["service"]["chrome"]["ports"]["http"]["port"])
    )
    assert_app_configuration(dataclasses.replace(app, values=values))


@pytest.mark.parametrize(
    "chart,sync,ignore",
    [
        ({"repo": "", "version": "1.0.0"}, {"wave": "0"}, []),
        ({"repo": "oci://example/chart", "version": ""}, {"wave": "0"}, []),
        ({"repo": "https://example/charts", "version": "1.0.0"}, {"wave": "0"}, []),
        ({"repo": "oci://example/chart", "version": "1.0.0"}, {}, []),
        ({"repo": "oci://example/chart", "version": "1.0.0"}, {"wave": "0"}, [{"group": ""}]),
        (
            {"repo": "oci://example/chart", "version": "1.0.0"},
            {"wave": "0"},
            [{"kind": "Deployment"}],
        ),
    ],
)
def test_metadata_required_fields(chart, sync, ignore):
    app = next(app for app in APPS if app.name == "karakeep")
    metadata = {"chart": chart, "sync": sync, "ignoreDifferences": ignore}
    with pytest.raises((AssertionError, KeyError)):
        assert_application(replace(app, metadata=metadata))


@pytest.mark.parametrize(
    "path,value",
    [
        ("/sonarr/web-2160p-v4/custom_format_groups", []),
        ("/sonarr/web-2160p-v4/custom_format_groups/add", {}),
        ("/radarr/uhd-bluray-web/custom_format_groups/add", [{}]),
        ("/sonarr/web-2160p-v4/media_naming/series", "other"),
        ("/radarr/uhd-bluray-web/media_naming/folder", "other"),
        ("/radarr/uhd-bluray-web/media_naming/movie/standard", "other"),
    ],
)
def test_recyclarr_configuration_regressions(path, value):
    import jsonpatch
    import yaml
    from tests.support.applications import assert_recyclarr, RecyclarrLoader

    app = next(app for app in APPS if app.name == "recyclarr")
    config = yaml.load(app.documents[0]["data"]["recyclarr.yml"], Loader=RecyclarrLoader)
    with pytest.raises(AssertionError):
        assert_recyclarr(
            jsonpatch.apply_patch(config, [{"op": "add", "path": path, "value": value}])
        )
