#!/usr/bin/env python3
"""Bootstrap the Kind-based homelab cluster and Flux Operator install."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

try:
    import yaml
except ImportError as exc:  # pragma: no cover - import guard
    sys.stderr.write("PyYAML is required to run bootstrap. Install it with 'pip install pyyaml'.\n")
    raise SystemExit(1) from exc


class BootstrapError(Exception):
    """Raised when a recoverable bootstrap error occurs."""


class ColorFormatter(logging.Formatter):
    COLORS = {
        logging.INFO: "\033[0;32m",
        logging.WARNING: "\033[1;33m",
        logging.ERROR: "\033[0;31m",
        logging.CRITICAL: "\033[0;31m",
    }
    RESET = "\033[0m"

    def __init__(self, use_color: bool) -> None:
        super().__init__("[%(asctime)s] %(levelname)s %(message)s", datefmt="%H:%M:%S")
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        if not self.use_color:
            return f"\n{base}"
        color = self.COLORS.get(record.levelno, "")
        return f"\n{color}{base}{self.RESET}"


def build_logger() -> logging.Logger:
    logger = logging.getLogger("home_ops.bootstrap")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(ColorFormatter(sys.stderr.isatty()))
        logger.addHandler(handler)
        logger.propagate = False
    return logger


class Bootstrapper:
    def __init__(self, delete_mode: bool) -> None:
        self.delete_mode = delete_mode

        # Environment defaults
        self.multus_iface = os.environ.get("MULTUS_PARENT_IFACE", "br0")
        self.multus_subnet = os.environ.get("MULTUS_PARENT_SUBNET", "192.168.1.0/24")
        self.multus_gateway = os.environ.get("MULTUS_PARENT_GATEWAY", "192.168.1.1")
        self.multus_ip_range = os.environ.get("MULTUS_PARENT_IP_RANGE", "192.168.1.240/29")

        # Filesystem layout
        self.project_root = Path(__file__).resolve().parent.parent
        self.cluster_config_root = self.project_root / "cluster" / "config"
        self.kind_config_path = self.cluster_config_root / "cluster-config.yaml"
        self.cluster_secrets_sops_path = self.cluster_config_root / "cluster-secrets.sops.yaml"
        self.default_kubeconfig = Path.home() / ".kube/config"
        self.default_age_key = self.project_root / ".sops.agekey"
        self.flux_instance_values_path = self.project_root / "infra" / "flux-system" / "flux-instance" / "app" / "helmrelease.yaml"
        self.flux_operator_helmrelease_path = self.project_root / "infra" / "flux-system" / "flux-operator" / "app" / "helmrelease.yaml"
        self.flux_operator_repo_path = self.project_root / "infra" / "flux-system" / "flux-operator" / "app" / "ocirepository.yaml"

        # Runtime/cache state
        self.cluster_name = ""
        self.docker_context = ""
        self.multus_network = ""
        self.bind_address = ""
        self.advertise_host = ""
        self.original_docker_context: Optional[str] = None
        self.cluster_secrets_data: Optional[Dict[str, Any]] = None
        self.decrypted_secrets_path: Optional[Path] = None
        self.flux_instance_name: Optional[str] = None
        self.flux_instance_namespace: Optional[str] = None
        self.flux_namespace: Optional[str] = None
        self.flux_sync_secret_name: Optional[str] = None
        self._temp_dir = tempfile.TemporaryDirectory(prefix="homelab-")

        self.env = os.environ.copy()
        self.logger = build_logger()

    # ------------------------------------------------------------ Core helpers
    def run(
        self,
        cmd: List[str],
        *,
        check: bool = True,
        capture_output: bool = False,
        env: Optional[Dict[str, str]] = None,
        stdout=None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            check=check,
            text=True,
            capture_output=capture_output,
            env=env or self.env,
            stdout=stdout,
        )

    @staticmethod
    def parse_host_port(server: str) -> Tuple[Optional[str], Optional[int]]:
        parsed = urlparse(server)
        if parsed.scheme and parsed.hostname and parsed.port:
            return parsed.hostname, parsed.port

        match = re.match(r"https?://([^:/]+):(\d+)", server)
        if match:
            return match.group(1), int(match.group(2))

        fallback = re.match(r".*:(\d+)$", server)
        if fallback:
            return None, int(fallback.group(1))
        return None, None

    def ensure_command(self, name: str) -> None:
        if shutil.which(name) is None:
            raise BootstrapError(f"[Deps] {name} is required but not found in PATH")

    def set_env_path(self, key: str, default_path: Optional[Path] = None) -> None:
        value = os.environ.get(key)
        if not value and default_path and default_path.exists():
            value = str(default_path)
        if value:
            self.env[key] = value

    def make_temp_file(self, suffix: str = ".yaml") -> Path:
        temp_dir_path = Path(self._temp_dir.name)
        temp_dir_path.mkdir(parents=True, exist_ok=True)
        fd, path = tempfile.mkstemp(prefix="tmp-", suffix=suffix, dir=temp_dir_path)
        os.close(fd)
        return Path(path)

    # -------------------------------------------------------------- Entry point
    def execute(self) -> None:
        self.init_environment()

        if self.delete_mode:
            self.logger.info(f"[Bootstrap] Starting delete workflow for cluster {self.cluster_name}")
            self.teardown_cluster()
            self.logger.info(f"[Bootstrap] Delete workflow complete for cluster {self.cluster_name}")
            return

        self.bootstrap_flow()

    def cleanup(self) -> None:
        self._temp_dir.cleanup()

        if self.original_docker_context and self.docker_context and self.original_docker_context != self.docker_context:
            subprocess.run(  # noqa: PLW1510 - best effort cleanup
                ["docker", "context", "use", self.original_docker_context],
                text=True,
                capture_output=True,
                check=False,
            )

    # ---------------------------------------------------- Environment bootstrap
    def init_environment(self) -> None:
        self.cluster_name = self.load_cluster_name()
        self.docker_context = f"kind-{self.cluster_name}"
        self.multus_network = f"kind-{self.cluster_name}-net"

        required = ["docker", "kind", "sops"]
        if not self.delete_mode:
            required.extend(["kubectl", "helm"])
        for command in required:
            self.ensure_command(command)

        self.prepare_docker_context()

        self.set_env_path("KUBECONFIG", self.default_kubeconfig)
        self.set_env_path("SOPS_AGE_KEY_FILE", self.default_age_key)

        self.logger.info(f"[Bootstrap] Targeting cluster {self.cluster_name} (context {self.docker_context})")
        self.logger.info(f"[Network] Using Multus iface={self.multus_iface}, subnet={self.multus_subnet}, " f"gateway={self.multus_gateway}, range={self.multus_ip_range}")

    def prepare_docker_context(self) -> None:
        contexts_output = self.run(["docker", "context", "ls", "--format", "{{.Name}}"], capture_output=True).stdout
        contexts = [ctx.strip() for ctx in contexts_output.splitlines()]
        if self.docker_context not in contexts:
            raise BootstrapError(f"[Docker] Context '{self.docker_context}' not found; create it before running bootstrap")

        current = (self.run(["docker", "context", "show"], check=False, capture_output=True).stdout or "default").strip()
        self.original_docker_context = current
        if current != self.docker_context:
            self.logger.info(f"[Docker] Switching context to {self.docker_context}")
            self.run(["docker", "context", "use", self.docker_context])

    def load_cluster_name(self) -> str:
        if not self.kind_config_path.exists():
            raise BootstrapError(f"[Config] Kind config {self.kind_config_path} does not exist")

        with self.kind_config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}

        name = data.get("name")
        if not name:
            raise BootstrapError(f"[Config] Kind config {self.kind_config_path} does not define a cluster name")
        return str(name)

    # ------------------------------------------------------- Main create flow
    def bootstrap_flow(self) -> None:
        self.logger.info(f"[Bootstrap] Starting create workflow for cluster {self.cluster_name}")
        self.detect_api_endpoint_settings()
        self.create_cluster()
        self.configure_macvlan_network()
        self.patch_kubeconfig_endpoint()
        self.use_kube_context()
        self.ensure_nodes_ready()
        self.strip_kindnet_resources()
        self.apply_cluster_secrets()
        self.deploy_flux_operator()
        self.apply_flux_sync_secret()
        self.apply_flux_instance()
        self.wait_for_flux_instance()
        self.logger.info(f"[Bootstrap] Complete; kubectl context is kind-{self.cluster_name}")

    # ---------------------------------------------------------- Cluster ops
    def detect_api_endpoint_settings(self) -> None:
        if self.advertise_host:
            return

        docker_host = self.inspect_docker_host(self.docker_context)
        host = docker_host or ""
        if host in ("127.0.0.1", "localhost"):
            host = ""

        self.advertise_host = host
        self.bind_address = "0.0.0.0" if host else ""

        if host:
            self.logger.info(f"[API] Exposing control plane on {host} (bind {self.bind_address})")
        else:
            self.logger.info("[API] Using local control plane endpoint")

    def use_kube_context(self) -> None:
        context = f"kind-{self.cluster_name}"

        current = (
            self.run(
                ["kubectl", "config", "current-context"],
                check=False,
                capture_output=True,
            ).stdout
            or ""
        ).strip()
        if current == context:
            self.logger.info(f"[Kubeconfig] Using context {context}")
            return

        contexts_output = self.run(
            ["kubectl", "config", "get-contexts", "-o", "name"],
            check=False,
            capture_output=True,
        ).stdout
        contexts = [line.strip() for line in contexts_output.splitlines() if line.strip()]
        if context not in contexts:
            raise BootstrapError(f"[Kubeconfig] Context '{context}' not found. Create the Kind cluster first or rerun bootstrap.")

        self.logger.info(f"[Kubeconfig] Switching kubectl context to {context}")
        self.run(["kubectl", "config", "use-context", context])

    def inspect_docker_host(self, context: str) -> str:
        output = self.run(["docker", "context", "inspect", context], check=False, capture_output=True).stdout
        if not output:
            return ""
        try:
            data = json.loads(output)[0]
        except (json.JSONDecodeError, IndexError, KeyError):
            return ""

        raw_host = data.get("Endpoints", {}).get("docker", {}).get("Host") or ""
        if not raw_host or raw_host.startswith(("unix://", "npipe://")):
            return ""

        parsed = urlparse(raw_host)
        if parsed.hostname:
            return parsed.hostname

        if "://" not in raw_host:
            return raw_host.split(":")[0]

        without_scheme = raw_host.split("://", 1)[-1]
        if "@" in without_scheme:
            without_scheme = without_scheme.split("@", 1)[-1]
        return without_scheme.split(":")[0]

    def create_cluster(self) -> None:
        tmp_config = self.make_temp_file(suffix=".yaml")
        with self.kind_config_path.open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle)

        if not isinstance(config, dict):
            raise BootstrapError(f"[Config] {self.kind_config_path} must be a YAML map")

        nodes = config.get("nodes") or []
        if not nodes or not nodes[0].get("kubeadmConfigPatches"):
            raise BootstrapError(f"[Config] {self.kind_config_path} must define nodes[0].kubeadmConfigPatches for the control plane")

        if self.bind_address:
            networking = config.setdefault("networking", {})
            networking["apiServerAddress"] = self.bind_address
            self.logger.info(f"[Config] Setting Kind apiServerAddress override to {self.bind_address}")

        with tmp_config.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(config, handle, sort_keys=False)

        if not self.cluster_exists():
            self.logger.info(f"[Cluster] Creating Kind cluster {self.cluster_name}")
            self.run(["kind", "create", "cluster", "--config", str(tmp_config)])
        elif self.bind_address or self.advertise_host:
            self.logger.warning(f"[Cluster] {self.cluster_name} already exists; rerun with --delete to apply updated API exposure settings")

    def cluster_exists(self) -> bool:
        clusters = self.run(["kind", "get", "clusters"], check=False, capture_output=True).stdout.splitlines()
        return any(line.strip() == self.cluster_name for line in clusters)

    def configure_macvlan_network(self) -> None:
        network_name = self.multus_network
        networks = self.run(["docker", "network", "ls", "--format", "{{.Name}}"], capture_output=True).stdout.splitlines()
        if network_name in networks:
            self.logger.info(f"[Network] Reusing Docker macvlan {network_name}")
        else:
            self.logger.info(f"[Network] Creating Docker macvlan {network_name} on {self.multus_iface} " f"(subnet {self.multus_subnet}, ip-range {self.multus_ip_range})")
            self.run(
                [
                    "docker",
                    "network",
                    "create",
                    "-d",
                    "macvlan",
                    "--subnet",
                    self.multus_subnet,
                    "--gateway",
                    self.multus_gateway,
                    "--ip-range",
                    self.multus_ip_range,
                    "-o",
                    f"parent={self.multus_iface}",
                    network_name,
                ]
            )

        result = self.run(
            ["kind", "get", "nodes", "--name", self.cluster_name],
            check=False,
            capture_output=True,
        ).stdout
        if not result:
            self.logger.warning(f"[Network] No nodes reported for cluster {self.cluster_name}; skipping macvlan attachment")
            return

        attached, unchanged = [], []
        for node in result.splitlines():
            node = node.strip()
            if not node or "control-plane" in node:
                continue
            completed = self.run(
                ["docker", "network", "connect", network_name, node],
                check=False,
            )
            if completed.returncode == 0:
                attached.append(node)
            else:
                unchanged.append(node)

        if attached:
            self.logger.info(f"[Network] Attached workers {' '.join(attached)} to {network_name}")
        if unchanged:
            self.logger.warning(f"[Network] Workers already attached to {network_name}: {' '.join(unchanged)}")
        if not attached and not unchanged:
            self.logger.info("[Network] No worker nodes eligible for macvlan attachment")

    def patch_kubeconfig_endpoint(self) -> None:
        if not self.advertise_host or not self.cluster_exists():
            return

        cluster_context = f"kind-{self.cluster_name}"
        raw = self.run(
            ["kubectl", "config", "view", "--raw", "-o", "json"],
            check=False,
            capture_output=True,
        ).stdout
        if not raw:
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        for cluster in data.get("clusters", []):
            if cluster.get("name") != cluster_context:
                continue
            server = cluster.get("cluster", {}).get("server", "")
            current_host, port = self.parse_host_port(server)

            if port is None:
                self.logger.warning(f"[Kubeconfig] Unable to parse API server port from '{server}'")
                return

            if current_host == self.advertise_host:
                return

            new_server = f"https://{self.advertise_host}:{port}"
            self.logger.info(f"[Kubeconfig] Patching server endpoint to {new_server}")
            self.run(
                [
                    "kubectl",
                    "config",
                    "set-cluster",
                    cluster_context,
                    f"--server={new_server}",
                ]
            )
            return

    def ensure_nodes_ready(self) -> None:
        self.logger.info("[Nodes] Waiting for all nodes to become Ready")
        self.run(
            [
                "kubectl",
                "wait",
                "--for=condition=Ready",
                "node",
                "--all",
                "--timeout=180s",
            ]
        )
        self.logger.info("[Nodes] All nodes are Ready")

    def strip_kindnet_resources(self) -> None:
        self.logger.info("[Network] Patching Kindnet to remove resource requests and limits")
        result = self.run(
            [
                "kubectl",
                "-n",
                "kube-system",
                "patch",
                "ds",
                "kindnet",
                "--type=json",
                "-p",
                '[{"op":"remove","path":"/spec/template/spec/containers/0/resources"}]',
            ],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            self.logger.warning("[Network] Failed to patch Kindnet (resources may already be absent)")

    def ensure_namespace_exists(self, namespace: str) -> None:
        namespace = (namespace or "").strip()
        if not namespace:
            return
        result = self.run(
            ["kubectl", "get", "namespace", namespace],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0:
            return
        self.logger.info(f"[Kubernetes] Creating namespace {namespace}")
        self.run(["kubectl", "create", "namespace", namespace])

    # ---------------------------------------------------------- Secrets & Flux
    def ensure_cluster_secrets_loaded(self) -> bool:
        if self.cluster_secrets_data is not None:
            return True
        if not self.cluster_secrets_sops_path.exists():
            return False

        tmp = self.make_temp_file(suffix=".yaml")
        with tmp.open("w", encoding="utf-8") as handle:
            self.run(
                ["sops", "--decrypt", str(self.cluster_secrets_sops_path)],
                env=self.env,
                stdout=handle,
            )

        with tmp.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise BootstrapError(f"[Secrets] {self.cluster_secrets_sops_path} must be a Secret manifest")

        self.cluster_secrets_data = data
        self.decrypted_secrets_path = tmp
        return True

    def apply_cluster_secrets(self) -> None:
        if not self.ensure_cluster_secrets_loaded():
            self.logger.warning(f"[Secrets] Cluster secret manifest skipped because {self.cluster_secrets_sops_path} is missing")
            return
        assert self.decrypted_secrets_path is not None
        metadata = (self.cluster_secrets_data or {}).get("metadata") or {}
        namespace = str(metadata.get("namespace") or "platform-system")
        self.ensure_namespace_exists(namespace)
        self.logger.info(f"[Secrets] Applying {self.cluster_secrets_sops_path} (decrypted)")
        self.run(["kubectl", "apply", "-f", str(self.decrypted_secrets_path)])

    def apply_flux_sync_secret(self) -> None:
        if not self.ensure_cluster_secrets_loaded():
            self.logger.warning("[Flux] Skipping Git credentials secret because cluster secrets are missing")
            return
        string_data = (self.cluster_secrets_data or {}).get("stringData") or {}
        username = string_data.get("flux_sync_username")
        password = string_data.get("flux_sync_password")
        if not username or not password:
            self.logger.info("[Flux] flux_sync_username/password not defined; assuming repository is public")
            return

        secret_name = self.get_flux_sync_secret_name()
        namespace = self.get_flux_namespace()
        secret_manifest = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": secret_name,
                "namespace": namespace,
            },
            "type": "kubernetes.io/basic-auth",
            "stringData": {
                "username": username,
                "password": password,
            },
        }
        tmp = self.make_temp_file(suffix=".yaml")
        with tmp.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(secret_manifest, handle, sort_keys=False)
        self.logger.info(f"[Flux] Applying Git credentials secret {secret_name} in {namespace}")
        self.run(["kubectl", "apply", "-f", str(tmp)])

    def deploy_flux_operator(self) -> None:
        chart, version = self.load_flux_operator_chart_info()
        namespace = self.get_flux_namespace()
        self.logger.info(f"[Flux] Installing flux-operator@{version} into namespace {namespace}")
        self.run(
            [
                "helm",
                "upgrade",
                "--install",
                "flux-operator",
                chart,
                "--namespace",
                namespace,
                "--create-namespace",
                "--version",
                version,
                "--wait",
            ]
        )
        self.logger.info("[Flux] Flux Operator installation completed")

    def load_flux_operator_chart_info(self) -> Tuple[str, str]:
        if not self.flux_operator_repo_path.exists():
            raise BootstrapError(f"[Flux] OCIRepository manifest not found at {self.flux_operator_repo_path}; expected infra/flux-system/flux-operator/app/ocirepository.yaml")
        with self.flux_operator_repo_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        spec = data.get("spec") or {}
        chart = spec.get("url")
        version = (spec.get("ref") or {}).get("tag")
        if not chart or not version:
            raise BootstrapError(f"[Flux] OCIRepository {self.flux_operator_repo_path} must define spec.url and spec.ref.tag")
        return str(chart), str(version)

    def get_flux_namespace(self) -> str:
        if self.flux_namespace:
            return self.flux_namespace
        if not self.flux_operator_helmrelease_path.exists():
            raise BootstrapError(f"[Flux] Flux operator HelmRelease not found at {self.flux_operator_helmrelease_path}")
        with self.flux_operator_helmrelease_path.open("r", encoding="utf-8") as handle:
            release = yaml.safe_load(handle) or {}
        metadata = release.get("metadata") or {}
        namespace = metadata.get("namespace", "flux-system")
        self.flux_namespace = str(namespace)
        return self.flux_namespace

    def render_flux_instance(self) -> Dict[str, Any]:
        if not self.flux_instance_values_path.exists():
            raise BootstrapError(f"[Flux] HelmRelease values missing at {self.flux_instance_values_path}; ensure infra/flux-system/flux-instance/app/helmrelease.yaml exists")
        with self.flux_instance_values_path.open("r", encoding="utf-8") as handle:
            release = yaml.safe_load(handle) or {}
        values = (((release.get("spec") or {}).get("values") or {}).get("instance")) or {}
        if not values:
            raise BootstrapError(f"[Flux] HelmRelease {self.flux_instance_values_path} must define spec.values.instance")
        metadata = release.get("metadata") or {}
        name = metadata.get("name", "flux")
        namespace = metadata.get("namespace", self.get_flux_namespace())
        self.flux_instance_name = name
        self.flux_instance_namespace = namespace
        if not self.flux_sync_secret_name:
            pull_secret = ((values.get("sync") or {}).get("pullSecret")) or "flux-sync"
            self.flux_sync_secret_name = str(pull_secret)
        return {
            "apiVersion": "fluxcd.controlplane.io/v1",
            "kind": "FluxInstance",
            "metadata": {"name": name, "namespace": namespace},
            "spec": values,
        }

    def get_flux_sync_secret_name(self) -> str:
        if self.flux_sync_secret_name:
            return self.flux_sync_secret_name
        self.render_flux_instance()
        assert self.flux_sync_secret_name is not None
        return self.flux_sync_secret_name

    def apply_flux_instance(self) -> None:
        manifest = self.render_flux_instance()
        assert self.flux_instance_name is not None
        assert self.flux_instance_namespace is not None
        self.logger.info(f"[Flux] Applying FluxInstance {self.flux_instance_name} in namespace {self.flux_instance_namespace}")
        temp_file = self.make_temp_file()
        temp_file.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
        try:
            self.run(["kubectl", "apply", "-f", str(temp_file)])
        finally:
            try:
                temp_file.unlink()
            except FileNotFoundError:  # pragma: no cover - best effort cleanup
                pass

    def wait_for_flux_instance(self) -> None:
        if not self.flux_instance_name or not self.flux_instance_namespace:
            self.render_flux_instance()
        assert self.flux_instance_name is not None
        assert self.flux_instance_namespace is not None
        self.logger.info(f"[Flux] Waiting for FluxInstance {self.flux_instance_name} in {self.flux_instance_namespace} to become Ready")
        self.run(
            [
                "kubectl",
                "-n",
                self.flux_instance_namespace,
                "wait",
                "--for=condition=Ready",
                f"fluxinstance/{self.flux_instance_name}",
                "--timeout=600s",
            ]
        )
        self.logger.info("[Flux] FluxInstance reports Ready")

    # ------------------------------------------------------------- Delete flow
    def teardown_cluster(self) -> None:
        if self.cluster_exists():
            self.logger.info(f"[Cluster] Deleting Kind cluster {self.cluster_name}")
            self.run(["kind", "delete", "cluster", "--name", self.cluster_name], check=False)
        else:
            self.logger.info(f"[Cluster] Skipping delete; cluster {self.cluster_name} not found")

        if self.multus_network:
            result = self.run(
                ["docker", "network", "rm", self.multus_network],
                check=False,
                capture_output=True,
            )
            if result.returncode == 0:
                self.logger.info(f"[Network] Removed Docker macvlan {self.multus_network}")
            else:
                self.logger.info(f"[Network] Skipping removal; Docker network {self.multus_network} not found")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap or delete the Kind-based homelab cluster.")
    parser.add_argument(
        "-d",
        "--delete",
        action="store_true",
        help="Delete the Kind cluster instead of creating it",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    bootstrapper = Bootstrapper(delete_mode=args.delete)
    try:
        bootstrapper.execute()
    except (BootstrapError, subprocess.CalledProcessError) as exc:
        message = str(exc)
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            message = f"{message}\n{exc.stderr.strip()}"
        bootstrapper.logger.error(message)
        raise SystemExit(1) from exc
    finally:
        bootstrapper.cleanup()


if __name__ == "__main__":  # pragma: no cover
    main()
