"""Pure data parsing and readiness predicates for secret-delivery roles."""
from datetime import datetime
import json
import tomllib


def from_toml(text):
    return tomllib.loads(text)


def safe_from_json(text):
    """Reject provider diagnostics without allowing parser exceptions into logs."""
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def platform_root_ready(resource, revision):
    sync = resource.get('status', {}).get('sync', {})
    revisions = sync.get('revisions', [])
    return sync.get('status') == 'Synced' and bool(revisions) and len(revisions) == len(resource.get('spec', {}).get('sources', [])) and all(item == revision for item in revisions)


def platform_secret_ready(resource, after_epoch):
    status = resource.get('status', {})
    if not any(item.get('type') == 'Ready' and item.get('status') == 'True' for item in status.get('conditions', [])):
        return False
    try:
        return datetime.fromisoformat(status['refreshTime'].replace('Z', '+00:00')).timestamp() >= float(after_epoch)
    except (KeyError, TypeError, ValueError):
        return False


def platform_owned_applications(resources, appset_uid):
    return [item['metadata']['name'] for item in resources if any(owner.get('uid') == appset_uid for owner in item['metadata'].get('ownerReferences', []))]


class FilterModule:
    def filters(self):
        return {
            'from_toml': from_toml,
            'safe_from_json': safe_from_json,
            'platform_root_ready': platform_root_ready,
            'platform_secret_ready': platform_secret_ready,
            'platform_owned_applications': platform_owned_applications,
        }
