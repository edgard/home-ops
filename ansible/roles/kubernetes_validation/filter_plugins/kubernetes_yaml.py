"""Safe Kubernetes YAML parsing shared by schema export and route coverage."""
import yaml
from ansible.errors import AnsibleFilterError


class KubernetesLoader(yaml.SafeLoader):
    pass


# An unquoted '=' is a legitimate label-selector default in chart CRDs.
# Register only this scalar tag; Python objects and other unsafe tags stay forbidden.
KubernetesLoader.add_constructor('tag:yaml.org,2002:value', KubernetesLoader.construct_scalar)


def from_kubernetes_yaml_all(text):
    try:
        return list(yaml.load_all(text, Loader=KubernetesLoader))
    except yaml.YAMLError:
        raise AnsibleFilterError('invalid-kubernetes-yaml') from None


class FilterModule:
    def filters(self):
        return {'from_kubernetes_yaml_all': from_kubernetes_yaml_all}
