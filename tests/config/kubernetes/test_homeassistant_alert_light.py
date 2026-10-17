import copy

import pytest
import yaml

from tests.support.sources import KubernetesLoader, applications


class HomeAssistantLoader(KubernetesLoader):
    pass


HomeAssistantLoader.add_multi_constructor(
    "!", lambda loader, tag, node: {"tag": tag, "path": loader.construct_scalar(node)}
)


def assert_alert_package(app, gatus):
    config = next(
        d
        for d in app.documents
        if d["metadata"]["name"] == "homeassistant-gatus-alert-light"
    )
    assert "gatus_alert_light.yaml" in config["data"], (
        "Missing native alert-light worker package"
    )
    package = yaml.safe_load(config["data"]["gatus_alert_light.yaml"])
    worker = package["script"]["gatus_alert_light_worker"]
    assert worker["mode"] == "queued" and worker["max"] == 100
    assert worker["variables"]["target_light"] == "light.office_office_mood_light"
    endpoints = worker["variables"]["endpoints"]
    expected = {
        "/".join(filter(None, [e.get("group", ""), e["name"]]))
        for e in gatus.values["config"]["endpoints"]
    }
    assert set(endpoints) == expected
    assert len(set(endpoints.values())) == len(endpoints)
    assert set(endpoints.values()) == {
        "input_boolean." + key for key in package["input_boolean"]
    }
    for helper in [*package["input_boolean"].values(), *package["input_text"].values()]:
        assert "initial" not in helper
    assert package["input_text"]["gatus_alert_light_snapshot"]["max"] == 255
    command = package["rest_command"]["gatus_alert_light_status"]
    assert (
        command["url"] == "http://gatus.platform-system.svc/api/v1/endpoints/statuses"
    )
    assert command["method"] == "GET" and command["timeout"] == 5
    main = next(
        d for d in app.documents if d["metadata"]["name"] == "homeassistant-config"
    )
    inner = yaml.load(main["data"]["configuration.yaml"], Loader=HomeAssistantLoader)
    assert inner["homeassistant"]["packages"] == {
        "tag": "include_dir_named",
        "path": "packages",
    }
    volume = app.values["persistence"]["config-gatus"]
    assert not volume.get("globalMounts")
    assert set(volume["advancedMounts"]["main"]) == {"app"}
    assert {m["path"] for m in volume["advancedMounts"]["main"]["app"]} == {
        "/config/packages/gatus_alert_light.yaml",
        "/config/custom_templates/gatus_alert_light.jinja",
    }
    assert all(m["readOnly"] for m in volume["advancedMounts"]["main"]["app"])


def test_native_alert_package_contract(repo_root):
    apps = {app.name: app for app in applications(repo_root)}
    assert_alert_package(apps["homeassistant"], apps["gatus"])


@pytest.mark.parametrize("broken", ["target", "catalog", "reset", "shared"])
def test_rejects_wrong_target_lost_state_and_shared_package(repo_root, broken):
    apps = {app.name: app for app in applications(repo_root)}
    app = copy.deepcopy(apps["homeassistant"])
    config = next(
        d
        for d in app.documents
        if d["metadata"]["name"] == "homeassistant-gatus-alert-light"
    )
    package = yaml.safe_load(config["data"]["gatus_alert_light.yaml"])
    if broken == "target":
        package["script"]["gatus_alert_light_worker"]["variables"]["target_light"] = (
            "light.unrelated"
        )
    elif broken == "catalog":
        package["script"]["gatus_alert_light_worker"]["variables"][
            "endpoints"
        ].popitem()
    elif broken == "reset":
        package["input_text"]["gatus_alert_light_snapshot"]["initial"] = ""
    else:
        app.values["persistence"]["config-gatus"]["globalMounts"] = [{"path": "/data"}]
    config["data"]["gatus_alert_light.yaml"] = yaml.safe_dump(package)
    with pytest.raises(AssertionError):
        assert_alert_package(app, apps["gatus"])


def test_rendered_alert_package_does_not_change_storage_or_matter(rendered):
    deployment = next(
        d
        for d in rendered
        if d["kind"] == "Deployment"
        and any(
            c["image"].startswith("ghcr.io/home-assistant/home-assistant:")
            for c in d["spec"]["template"]["spec"]["containers"]
        )
    )
    pod = deployment["spec"]["template"]["spec"]
    containers = {c["name"]: c for c in pod["containers"]}
    mounts = containers["app"]["volumeMounts"]
    wanted = {
        "/config/packages/gatus_alert_light.yaml",
        "/config/custom_templates/gatus_alert_light.jinja",
    }
    selected = [m for m in mounts if m["mountPath"] in wanted]
    assert len(selected) == 2 and all(m["readOnly"] for m in selected)
    names = {m["name"] for m in selected}
    assert not names.intersection(
        m["name"] for m in containers["matter-server"]["volumeMounts"]
    )
    assert {
        v["persistentVolumeClaim"]["claimName"]
        for v in pod["volumes"]
        if "persistentVolumeClaim" in v
    } == {"homeassistant", deployment["metadata"]["name"] + "-matter"}
