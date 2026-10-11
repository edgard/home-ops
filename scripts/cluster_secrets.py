#!/usr/bin/env python3
"""Bounded GitOps handoff checks and narrowly scoped ESO token replacement."""
import argparse
import base64
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import time
import yaml
from kubernetes import client, config

from bootstrap import PreflightError, application_access

ROOT = Path(__file__).resolve().parents[1]


class ClusterError(Exception):
    """Safe stage/resource description without API payloads."""


def root_ready(resource, revision):
    sync = resource.get('status', {}).get('sync', {})
    revisions = sync.get('revisions', [])
    return sync.get('status') == 'Synced' and len(revisions) == len(resource.get('spec', {}).get('sources', [])) and bool(revisions) and all(item == revision for item in revisions)


def secret_ready(resource, after):
    status = resource.get('status', {})
    if not any(item.get('type') == 'Ready' and item.get('status') == 'True' for item in status.get('conditions', [])):
        return False
    try:
        return datetime.fromisoformat(status['refreshTime'].replace('Z', '+00:00')) >= after
    except (KeyError, ValueError, TypeError):
        return False


def inventory():
    result = []
    for path in sorted(ROOT.glob('apps/*/*/manifests/*.yaml')):
        for document in yaml.safe_load_all(path.read_text()):
            if isinstance(document, dict) and document.get('kind') == 'ExternalSecret':
                result.append(document)
    return result


def get_resource(api, group, version, plural, name, namespace=None):
    try:
        if namespace:
            return api.get_namespaced_custom_object(group, version, namespace, plural, name, _request_timeout=10)
        return api.get_cluster_custom_object(group, version, plural, name, _request_timeout=10)
    except client.ApiException as error:
        if error.status == 404:
            return {}
        raise ClusterError(f'api-read-failed:{plural}/{name}') from None
    except Exception:
        raise ClusterError(f'api-read-failed:{plural}/{name}') from None


def wait_until(check, seconds, stage):
    deadline = time.monotonic() + seconds
    pending = stage
    while time.monotonic() < deadline:
        pending = check()
        if not pending:
            return
        time.sleep(min(5, max(0, deadline - time.monotonic())))
    raise ClusterError(f'{stage}-timeout:{pending}')


def wait_handoff(api, revision):
    expected = {path.parent.name for path in ROOT.glob('apps/*/*/app.yaml')}
    def check():
        root = get_resource(api, 'argoproj.io', 'v1alpha1', 'applications', 'root', 'argocd')
        if not root_ready(root, revision):
            return 'Application/root-revision'
        appset = get_resource(api, 'argoproj.io', 'v1alpha1', 'applicationsets', 'apps', 'argocd')
        uid = appset.get('metadata', {}).get('uid')
        if not uid:
            return 'ApplicationSet/apps'
        try:
            applications = api.list_namespaced_custom_object('argoproj.io', 'v1alpha1', 'argocd', 'applications', _request_timeout=10)['items']
        except Exception:
            raise ClusterError('application-list-failed') from None
        children = {item['metadata']['name'] for item in applications if any(owner.get('uid') == uid for owner in item['metadata'].get('ownerReferences', []))}
        missing = expected - children
        return 'Application/' + sorted(missing)[0] if missing else ''
    wait_until(check, 300, 'root-handoff')


def wait_secrets(api, after):
    manifests = inventory()
    def check():
        store = get_resource(api, 'external-secrets.io', 'v1', 'clustersecretstores', 'external-secrets-store')
        if not any(item.get('type') == 'Ready' and item.get('status') == 'True' for item in store.get('status', {}).get('conditions', [])):
            return 'ClusterSecretStore/external-secrets-store'
        for manifest in manifests:
            meta = manifest['metadata']
            resource = get_resource(api, 'external-secrets.io', 'v1', 'externalsecrets', meta['name'], meta['namespace'])
            if not secret_ready(resource, after):
                return f"ExternalSecret/{meta['namespace']}/{meta['name']}"
            # Inspect the target without printing or persisting credential values.
            target = manifest['spec']['target']['name']
            try:
                secret = client.CoreV1Api(api.api_client).read_namespaced_secret(target, meta['namespace'], _request_timeout=10)
            except Exception:
                raise ClusterError(f"target-secret-read-failed:{meta['namespace']}/{target}") from None
            expected_keys = set(manifest['spec']['target'].get('template', {}).get('data', {})) or {item['secretKey'] for item in manifest['spec']['data']}
            if not expected_keys.issubset(secret.data or {}):
                return f"Secret/{meta['namespace']}/{target}-keys"
        return ''
    wait_until(check, 600, 'application-secret-reconciliation')


def read_token(api):
    try:
        secret = client.CoreV1Api(api.api_client).read_namespaced_secret('bitwarden-credentials', 'platform-system', _request_timeout=10)
        return base64.b64decode(secret.data['token']).decode()
    except Exception:
        raise ClusterError('previous-eso-token-unavailable') from None


def replace_token(api, token):
    try:
        # Strategic merge patches only this one key and preserves Secret metadata.
        client.CoreV1Api(api.api_client).patch_namespaced_secret('bitwarden-credentials', 'platform-system', {'stringData': {'token': token}}, _request_timeout=10)
    except Exception:
        raise ClusterError('eso-token-update-failed') from None


def sync_token(api, token):
    application_access(token)
    previous = read_token(api)
    started = datetime.now(timezone.utc)
    try:
        replace_token(api, token)
        wait_secrets(api, started)
    except Exception:
        try:
            replace_token(api, previous)
        except Exception:
            raise ClusterError('reconciliation-failed:previous-token-restore-failed') from None
        raise ClusterError('reconciliation-failed:previous-token-restored') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['handoff', 'sync-token'])
    parser.add_argument('--revision')
    parser.add_argument('--kubeconfig', default=os.environ.get('KUBECONFIG', str(Path.home() / '.kube/config')))
    parser.add_argument('--context', default=os.environ.get('KUBE_CONTEXT', 'admin@' + os.environ.get('TALOS_CLUSTER_NAME', 'homelab')))
    args = parser.parse_args()
    try:
        config.load_kube_config(config_file=args.kubeconfig, context=args.context)
        api = client.CustomObjectsApi()
        if args.action == 'sync-token':
            token = os.environ.get('ESO_BWS_ACCESS_TOKEN', '')
            if not token:
                raise ClusterError('missing-scoped-eso-token')
            sync_token(api, token)
        else:
            if not args.revision:
                raise ClusterError('expected-revision-required')
            started = datetime.now(timezone.utc)
            wait_handoff(api, args.revision)
            wait_secrets(api, started)
        print('Cluster secret verification passed')
        return 0
    except Exception as error:
        # Only our categorical exceptions are safe to display.
        detail = str(error) if isinstance(error, ClusterError) else 'cluster-secret-verification-failed'
        if isinstance(error, PreflightError):
            detail = 'replacement-token-rejected:' + str(error)
        print(detail, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
