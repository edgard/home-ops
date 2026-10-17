import copy
import ipaddress
import json

import json5
import pytest

from tests.support.sources import applications


@pytest.fixture
def homeassistant(repo_root):
    return next(app for app in applications(repo_root) if app.name == "homeassistant")


def assert_matter_configuration(app):
    values = app.values
    controller = values["controllers"]["main"]
    assert "matter-server" in controller["containers"], "Matter shares the HA pod"
    matter = controller["containers"]["matter-server"]
    env = matter["env"]
    assert ipaddress.ip_address(env["LISTEN_ADDRESS"]).is_loopback
    assert env["STORAGE_PATH"] == "/data"
    security = matter["securityContext"]
    assert security["runAsNonRoot"] is True
    assert security["runAsUser"] == security["runAsGroup"] == 1000
    assert not security.get("privileged", False)
    assert security["allowPrivilegeEscalation"] is False
    assert "ALL" in security["capabilities"]["drop"]
    assert not security["capabilities"].get("add")
    pod = controller["pod"]
    assert not pod.get("hostNetwork", False)
    attachments = json.loads(pod["annotations"]["k8s.v1.cni.cncf.io/networks"])
    assert len(attachments) == 1
    attachment = attachments[0]
    assert attachment["interface"] == env["PRIMARY_INTERFACE"]
    network = next(
        doc
        for doc in app.documents
        if doc["kind"] == "NetworkAttachmentDefinition"
        and doc["metadata"]["name"] == attachment["name"]
        and doc["metadata"]["namespace"] == attachment["namespace"]
    )
    assert int(network["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]) < 0
    plugins = json.loads(network["spec"]["config"])["plugins"]
    bridge, tuning = plugins
    assert bridge["type"] == "bridge" and bridge["bridge"] == "br0"
    assert bridge["ipam"]["type"] == "static"
    assert not bridge.get("isGateway", False)
    assert tuning["type"] == "tuning"
    sysctls = tuning["sysctl"]
    assert sysctls["net.ipv6.conf.IFNAME.disable_ipv6"] == "0"
    assert sysctls["net.ipv6.conf.IFNAME.autoconf"] == "1"
    assert sysctls["net.ipv6.conf.IFNAME.accept_ra"] == "1"
    assert sysctls["net.ipv6.conf.IFNAME.accept_ra_rtr_pref"] == "1"
    assert int(sysctls["net.ipv6.conf.IFNAME.accept_ra_rt_info_max_plen"]) >= 64
    assert sysctls["net.ipv6.conf.all.forwarding"] == "0"
    persistence = values["persistence"]
    matter_data = persistence["matter"]
    assert matter_data["type"] == "persistentVolumeClaim"
    assert matter_data["storageClass"] == "nfs-fast"
    assert matter_data["annotations"]["argocd.argoproj.io/sync-options"] == (
        "Prune=false,Delete=false"
    )
    assert not matter_data.get("globalMounts")
    assert matter_data["advancedMounts"] == {
        "main": {"matter-server": [{"path": "/data"}]}
    }
    assert "globalMounts" not in persistence["data"]
    assert set(persistence["data"]["advancedMounts"]["main"]) == {"app"}
    assert "globalMounts" not in persistence["config-main"]


def test_homeassistant_matter_configuration(homeassistant):
    assert_matter_configuration(homeassistant)


@pytest.mark.parametrize("broken", ["wildcard", "ephemeral", "shared", "no-route-info"])
def test_matter_rejects_exposure_data_loss_and_missing_routes(homeassistant, broken):
    app = copy.deepcopy(homeassistant)
    if broken == "wildcard":
        app.values["controllers"]["main"]["containers"]["matter-server"]["env"][
            "LISTEN_ADDRESS"
        ] = "0.0.0.0"
    elif broken == "ephemeral":
        app.values["persistence"]["matter"]["type"] = "emptyDir"
    elif broken == "shared":
        app.values["persistence"]["matter"]["globalMounts"] = [{"path": "/data"}]
    else:
        network = next(
            doc for doc in app.documents if doc["kind"] == "NetworkAttachmentDefinition"
        )
        config = json.loads(network["spec"]["config"])
        config["plugins"][1]["sysctl"][
            "net.ipv6.conf.IFNAME.accept_ra_rt_info_max_plen"
        ] = "0"
        network["spec"]["config"] = json.dumps(config)
    with pytest.raises(AssertionError):
        assert_matter_configuration(app)


def test_rendered_matter_volume_and_listener_isolation(rendered):
    deployment = next(
        doc
        for doc in rendered
        if doc["kind"] == "Deployment"
        and any(
            container["image"].startswith("ghcr.io/home-assistant/home-assistant:")
            for container in doc["spec"]["template"]["spec"]["containers"]
        )
    )
    pod = deployment["spec"]["template"]["spec"]
    containers = {container["name"]: container for container in pod["containers"]}
    assert "matter-server" in containers
    matter = containers["matter-server"]
    env = {entry["name"]: entry.get("value") for entry in matter["env"]}
    assert env["LISTEN_ADDRESS"] == "127.0.0.1"
    claims = {
        volume["name"]: volume["persistentVolumeClaim"]["claimName"]
        for volume in pod["volumes"]
        if "persistentVolumeClaim" in volume
    }
    matter_mounts = matter["volumeMounts"]
    assert len(matter_mounts) == 1 and matter_mounts[0]["mountPath"] == "/data"
    matter_volume = matter_mounts[0]["name"]
    assert matter_volume in claims
    assert all(
        mount["name"] != matter_volume for mount in containers["app"]["volumeMounts"]
    )
    assert {claims[mount["name"]] for mount in matter_mounts}.isdisjoint(
        claims[mount["name"]]
        for mount in containers["app"]["volumeMounts"]
        if mount["name"] in claims
    )
    startup = matter["startupProbe"]
    assert startup["failureThreshold"] * startup["periodSeconds"] >= 900
    assert startup["exec"]["command"] == ["/usr/local/bin/healthcheck.sh"]
    for doc in rendered:
        if doc["kind"] == "Service":
            assert all(port["port"] != 5580 for port in doc["spec"]["ports"])


def test_matter_updates_require_manual_review(repo_root):
    config = json5.loads((repo_root / ".renovaterc.json5").read_text())
    package = "ghcr.io/matter-js/matterjs-server"
    for update in ("major", "minor", "patch", "digest", "pin", "rollback"):
        effective = {}
        for rule in config["packageRules"]:
            names = rule.get("matchPackageNames", [])
            if names and not any(
                name == package or (name.startswith("!") and name[1:] != package)
                for name in names
            ):
                continue
            if "matchUpdateTypes" in rule and update not in rule["matchUpdateTypes"]:
                continue
            if rule.get("matchDatasources", ["docker"]) != ["docker"]:
                continue
            effective.update(rule)
        assert effective.get("automerge") is False
        assert effective.get("groupName") == "matter-server"
