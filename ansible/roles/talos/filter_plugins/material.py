"""Validate secret YAML without surfacing parser excerpts in Ansible errors."""

import yaml


def valid_talos_material(text):
    fields = {
        "cluster": ("id", "secret"),
        "secrets": ("bootstraptoken", "secretboxencryptionsecret"),
        "trustdinfo": ("token",),
        "certs": ("etcd", "k8s", "k8saggregator", "k8sserviceaccount", "os"),
    }
    try:
        data = yaml.safe_load(text)
        return isinstance(data, dict) and all(
            isinstance(data.get(section), dict)
            and all(data[section].get(field) for field in keys)
            for section, keys in fields.items()
        )
    except TypeError, ValueError, yaml.YAMLError:
        return False


class FilterModule:
    def filters(self):
        return {"valid_talos_material": valid_talos_material}
