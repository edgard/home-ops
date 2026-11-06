"""Small nonsecret transformations shared by data-operation tasks."""

from datetime import datetime


def image_map(results):
    images = {}
    for row in results:
        if len(row.get("resources", [])) != 1:
            raise ValueError(
                "registered workload missing while recording image identities"
            )
        app = row["item"][0]["key"]
        pod = row["resources"][0]["spec"]["template"]["spec"]
        images.setdefault(app, []).extend(
            container["image"]
            for key in ["initContainers", "containers"]
            for container in pod.get(key, [])
        )
    return images


def newer_capture(current, candidate):
    captured = datetime.fromisoformat(candidate["captured_at"])
    if captured.tzinfo is None:
        raise ValueError("backup capture requires an explicit timezone")
    previous = current.get("data", {}).get("captured_at")
    if not previous:
        return True
    previous = datetime.fromisoformat(previous)
    if previous.tzinfo is None:
        raise ValueError("stored backup capture has an ambiguous timezone")
    return captured > previous


def redis_apps(registry, apps):
    return [
        name
        for name in apps
        if name in registry["consumers"]
        and registry["consumers"][name].get("redis")
        and registry["consumers"][name]["redis"].get("adopted", True)
    ]


class FilterModule:
    def filters(self):
        return {
            "shared_data_image_map": image_map,
            "shared_data_newer_capture": newer_capture,
            "shared_data_redis_apps": redis_apps,
        }
