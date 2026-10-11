"""Local Kubernetes HTTP fixture; synthetic values only, never a cluster client."""
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

root = Path(sys.argv[1])


def state():
    return json.loads((root / 'api-state.json').read_text())


def save(value):
    (root / 'api-state.json').write_text(json.dumps(value))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def respond(self, value, code=200):
        data = json.dumps(value).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/version':
            return self.respond({'major': '1', 'minor': '35', 'gitVersion': 'v1.35.0'})
        if path == '/api':
            return self.respond({'kind': 'APIVersions', 'apiVersion': 'v1', 'versions': ['v1']})
        if path == '/apis':
            return self.respond({'kind': 'APIGroupList', 'apiVersion': 'v1', 'groups': [{
                'name': 'external-secrets.io',
                'versions': [{'groupVersion': 'external-secrets.io/v1', 'version': 'v1'}],
                'preferredVersion': {'groupVersion': 'external-secrets.io/v1', 'version': 'v1'},
            }, {'name': 'argoproj.io', 'versions': [{'groupVersion': 'argoproj.io/v1alpha1', 'version': 'v1alpha1'}], 'preferredVersion': {'groupVersion': 'argoproj.io/v1alpha1', 'version': 'v1alpha1'}}]})
        if path in ('/api/v1', '/apis/external-secrets.io/v1', '/apis/argoproj.io/v1alpha1'):
            resources = [('secrets', 'Secret', True)] if path == '/api/v1' else [
                ('clustersecretstores', 'ClusterSecretStore', False), ('externalsecrets', 'ExternalSecret', True)]
            if path == '/apis/argoproj.io/v1alpha1':
                resources = [('applications', 'Application', True), ('applicationsets', 'ApplicationSet', True)]
            return self.respond({'kind': 'APIResourceList', 'apiVersion': 'v1',
                                 'groupVersion': 'v1' if path == '/api/v1' else path.removeprefix('/apis/'),
                                 'resources': [{'name': name, 'singularName': '', 'kind': kind, 'namespaced': namespaced,
                                                'verbs': ['get', 'list', 'patch', 'create']} for name, kind, namespaced in resources]})
        current = state()
        current['reads'].append(path)
        save(current)
        name = path.rsplit('/', 1)[-1]
        if path.endswith('/applications/root'):
            current['root_reads'] = current.get('root_reads', 0) + 1
            save(current)
            revision = 'synthetic-old-head' if current['scenario'] == 'root-advanced' and current['root_reads'] > 1 else 'synthetic-merged-head'
            return self.respond({'apiVersion': 'argoproj.io/v1alpha1', 'kind': 'Application',
                                 'metadata': {'name': 'root', 'namespace': 'argocd'}, 'spec': {'sources': [{}, {}, {}]},
                                 'status': {'sync': {'status': 'Synced', 'revisions': [revision] * 3}}})
        if path.endswith('/applicationsets/apps'):
            current['appset_reads'] = current.get('appset_reads', 0) + 1
            save(current)
            uid = 'new-appset-owner' if current['scenario'] == 'appset-recreated' and current['appset_reads'] > 1 else 'fixture-appset-owner'
            return self.respond({'apiVersion': 'argoproj.io/v1alpha1', 'kind': 'ApplicationSet',
                                 'metadata': {'name': 'apps', 'namespace': 'argocd', 'uid': uid}})
        if path.endswith('/applications'):
            return self.respond({'apiVersion': 'argoproj.io/v1alpha1', 'kind': 'ApplicationList',
                                 'items': [{'apiVersion': 'argoproj.io/v1alpha1', 'kind': 'Application',
                                            'metadata': {'name': item, 'namespace': 'argocd', 'ownerReferences': [{'uid': 'fixture-appset-owner'}]}}
                                           for item in current['applications']]})
        if path.startswith('/api/v1/namespaces/') and '/secrets/' in path:
            namespace = path.split('/')[4]
            if (current['scenario'] == 'previous-read-failure' and name == 'bitwarden-credentials') or (current['scenario'] == 'target-read-failure' and name != 'bitwarden-credentials'):
                return self.respond({'kind': 'Status', 'apiVersion': 'v1', 'message': 'SYNTHETIC-PRIVATE-API-DIAGNOSTIC', 'reason': 'Forbidden', 'code': 403}, 403)
            data = {'token': current['token']} if name == 'bitwarden-credentials' else current['target_keys']
            if current['scenario'] == 'malformed-previous-token' and name == 'bitwarden-credentials':
                data = {'token': 'not-base64!'}
            if current['scenario'] == 'missing-previous-token' and name == 'bitwarden-credentials':
                data = {}
            return self.respond({'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {
                'name': name, 'namespace': namespace, 'resourceVersion': '1', 'uid': 'fixture-secret'}, 'data': data, 'type': 'Opaque'})
        if '/clustersecretstores/' in path:
            if current['scenario'] == 'store-read-failure':
                return self.respond({'kind': 'Status', 'apiVersion': 'v1', 'message': 'SYNTHETIC-PRIVATE-API-DIAGNOSTIC', 'reason': 'Forbidden', 'code': 403}, 403)
            return self.respond({'apiVersion': 'external-secrets.io/v1', 'kind': 'ClusterSecretStore',
                                 'metadata': {'name': name}, 'status': {'conditions': [{'type': 'Ready', 'status': 'True'}]}})
        if '/externalsecrets/' in path:
            if current['scenario'] == 'es-read-failure':
                return self.respond({'kind': 'Status', 'apiVersion': 'v1', 'message': 'SYNTHETIC-PRIVATE-API-DIAGNOSTIC', 'reason': 'Forbidden', 'code': 403}, 403)
            ready = 'False' if current['scenario'] in ('reconciliation-failure', 'restore-failure') else 'True'
            return self.respond({'apiVersion': 'external-secrets.io/v1', 'kind': 'ExternalSecret',
                                 'metadata': {'name': name, 'namespace': path.split('/')[5]}, 'status': {
                                     'refreshTime': '2100-01-01T00:00:00Z', 'conditions': [{'type': 'Ready', 'status': ready}]}})
        self.respond({'kind': 'Status', 'apiVersion': 'v1', 'status': 'Failure', 'reason': 'NotFound', 'code': 404}, 404)

    def do_PATCH(self):
        current = state()
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        value = payload.get('data', {}).get('token')
        if 'token' in payload.get('stringData', {}):
            value = base64.b64encode(payload['stringData']['token'].encode()).decode()
        if value is None or (set(payload.get('data', {})) | set(payload.get('stringData', {}))) != {'token'}:
            return self.respond({'kind': 'Status', 'message': 'fixture rejects broad secret patch', 'code': 422}, 422)
        current['patches'].append(value)
        current['token'] = value
        save(current)
        if current['scenario'] == 'ambiguous-patch' and len(current['patches']) == 1:
            return self.respond({'kind': 'Status', 'apiVersion': 'v1', 'status': 'Failure',
                                 'reason': 'InternalError', 'message': 'SYNTHETIC-PRIVATE-API-DIAGNOSTIC', 'code': 500}, 500)
        if current['scenario'] == 'restore-failure' and len(current['patches']) > 1:
            return self.respond({'kind': 'Status', 'apiVersion': 'v1', 'status': 'Failure', 'message': 'SYNTHETIC-PRIVATE-API-DIAGNOSTIC', 'code': 500}, 500)
        return self.respond({'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {
            'name': 'bitwarden-credentials', 'namespace': 'platform-system', 'resourceVersion': '2'}, 'data': {'token': value}})


server = HTTPServer(('127.0.0.1', 0), Handler)
server.timeout = 0.2
(root / 'api-port').write_text(str(server.server_address[1]))
while not (root / 'api-stop').exists():
    server.handle_request()
server.server_close()
