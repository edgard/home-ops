#!/usr/bin/env python3
"""Bootstrap the Kind-based homelab cluster and Argo CD install."""

from __future__ import annotations

import argparse
import json
import logging
import os
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
            return base
        color = self.COLORS.get(record.levelno, "")
        return f"{color}{base}{self.RESET}"


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
        self.project_root = Path(__file__).resolve().parents[2]
        self.cluster_config_root = self.project_root / "bootstrap" / "config"
        self.kind_config_path = self.cluster_config_root / "cluster-config.yaml"
        self.cluster_credentials_sops_path = self.cluster_config_root / "cluster-credentials.sops.yaml"
        self.default_kubeconfig = Path.home() / ".kube/config"
        self.default_age_key = self.project_root / ".sops.agekey"
        self.helmfile_path = self.project_root / "bootstrap" / "config" / "helmfile.yaml.gotmpl"

        # Runtime/cache state
        self.cluster_name = ""
        self.bind_address = ""
        self.advertise_host = ""
        self.original_docker_context: Optional[str] = None
        self.cluster_credentials_data: Optional[Dict[str, Any]] = None
        self.decrypted_secrets_path: Optional[Path] = None
        self._temp_dir = tempfile.TemporaryDirectory(prefix="homelab-")

        self.env = os.environ.copy()
        self.logger = build_logger()

    @property
    def kind_context(self) -> str:
        return f"kind-{self.cluster_name}"

    @property
    def docker_context(self) -> str:
        return self.kind_context

    @property
    def multus_network(self) -> str:
        return f"{self.kind_context}-net"

    def ensure_command(self, name: str) -> None:
        if shutil.which(name) is None:
            raise BootstrapError(f"[Deps] {name} is required but not found in PATH")

    def run_prebootstrap_helmfile(self, run_helmfile: bool) -> None:
        """
        Apply pre-Argo dependencies (storage, CNI, ArgoCD) via helmfile in declared order.
        """
        if self.delete_mode or not run_helmfile:
            return
        if not self.helmfile_path.exists():
            self.logger.warning(f"[Helmfile] Not found at {self.helmfile_path}, skipping prebootstrap sync")
            return
        self.logger.info(f"[Helmfile] Syncing prebootstrap dependencies file={self.helmfile_path}")
        self.run(
            [
                "helmfile",
                "-f",
                str(self.helmfile_path),
                "sync",
            ]
        )

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

    # --------------------------------------------------------- Execution flow
    def execute(self) -> None:
        self.init_environment()

        if self.delete_mode:
            self.logger.info(f"[Bootstrap] Starting delete workflow cluster={self.cluster_name}")
            self.teardown_cluster()
            self.logger.info(f"[Bootstrap] Delete workflow complete cluster={self.cluster_name}")
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

    # ---------------------------------------------------- Environment & dependencies
    def init_environment(self) -> None:
        self.cluster_name = self.load_cluster_name()

        required = ["docker", "kind", "sops", "helmfile"]
        if not self.delete_mode:
            required.extend(["kubectl", "helm"])
        for command in required:
            self.ensure_command(command)

        self.prepare_docker_context()

        self.set_env_path("KUBECONFIG", self.default_kubeconfig)
        self.set_env_path("SOPS_AGE_KEY_FILE", self.default_age_key)

        self.logger.info(f"[Bootstrap] Targeting cluster name={self.cluster_name} context={self.docker_context}")
        self.logger.info(f"[Network] Using Multus iface={self.multus_iface} subnet={self.multus_subnet} " f"gateway={self.multus_gateway} range={self.multus_ip_range}")

    def prepare_docker_context(self) -> None:
        contexts_output = self.run(["docker", "context", "ls", "--format", "{{.Name}}"], capture_output=True).stdout
        contexts = [ctx.strip() for ctx in contexts_output.splitlines()]
        if self.docker_context not in contexts:
            raise BootstrapError(f"[Docker] Context not found name={self.docker_context} action=create-context-before-bootstrap")

        current = (self.run(["docker", "context", "show"], check=False, capture_output=True).stdout or "default").strip()
        self.original_docker_context = current
        if current != self.docker_context:
            self.logger.info(f"[Docker] Switching context to context={self.docker_context}")
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

    # ------------------------------------------------------- Create workflow
    def bootstrap_flow(self) -> None:
        self.logger.info(f"[Bootstrap] Starting create workflow cluster={self.cluster_name}")
        self.detect_api_endpoint_settings()
        created = self.create_cluster()
        self.configure_macvlan_network()
        self.patch_kubeconfig_endpoint()
        self.use_kube_context()
        self.ensure_nodes_ready()
        self.strip_kindnet_resources()
        self.apply_cluster_secrets()
        self.preload_busybox_image()
        self.run_prebootstrap_helmfile(created)
        self.logger.info(f"[Bootstrap] Complete kubectl-context={self.kind_context}")

    # -------------------------------------------------- Cluster & networking
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
            self.logger.info(f"[API] Exposing control plane host={host} bind={self.bind_address}")
        else:
            self.logger.info("[API] Using local control plane endpoint")

    def use_kube_context(self) -> None:
        current = (
            self.run(
                ["kubectl", "config", "current-context"],
                check=False,
                capture_output=True,
            ).stdout
            or ""
        ).strip()
        if current == self.kind_context:
            self.logger.info(f"[Kubeconfig] Using context={self.kind_context}")
            return

        contexts_output = self.run(
            ["kubectl", "config", "get-contexts", "-o", "name"],
            check=False,
            capture_output=True,
        ).stdout
        contexts = [line.strip() for line in contexts_output.splitlines() if line.strip()]
        if self.kind_context not in contexts:
            raise BootstrapError(f"[Kubeconfig] Context '{self.kind_context}' not found. Create the Kind cluster first or rerun bootstrap.")

        self.logger.info(f"[Kubeconfig] Switching kubectl context to context={self.kind_context}")
        self.run(["kubectl", "config", "use-context", self.kind_context])

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

    def create_cluster(self) -> bool:
        with self.kind_config_path.open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle)

        if not isinstance(config, dict):
            raise BootstrapError(f"[Config] {self.kind_config_path} must be a YAML map")

        nodes = config.get("nodes") or []
        if not nodes or not nodes[0].get("kubeadmConfigPatches"):
            raise BootstrapError(f"[Config] {self.kind_config_path} must define nodes[0].kubeadmConfigPatches for the control plane")

        config_path: Path = self.kind_config_path
        if self.bind_address:
            tmp_config = self.make_temp_file(suffix=".yaml")
            networking = config.setdefault("networking", {})
            networking["apiServerAddress"] = self.bind_address
            self.logger.info(f"[Config] Setting Kind apiServerAddress={self.bind_address}")
            with tmp_config.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(config, handle, sort_keys=False)
            config_path = tmp_config

        if not self.cluster_exists():
            self.logger.info(f"[Cluster] Creating Kind cluster name={self.cluster_name}")
            self.run(["kind", "create", "cluster", "--config", str(config_path)])
            return True
        else:
            if self.bind_address or self.advertise_host:
                current_host, _ = self.current_api_server_endpoint()
                if current_host and current_host != self.advertise_host:
                    raise BootstrapError(f"[Cluster] API host mismatch name={self.cluster_name} current={current_host} " f"expected={self.advertise_host} action=recreate-with-delete")
                if current_host is None:
                    raise BootstrapError(f"[Cluster] API host unknown name={self.cluster_name} action=recreate-with-delete")
            self.logger.info(f"[Cluster] Skipping create reason=cluster-exists name={self.cluster_name}")
            return False

    def cluster_exists(self) -> bool:
        clusters = self.run(["kind", "get", "clusters"], check=False, capture_output=True).stdout.splitlines()
        return any(line.strip() == self.cluster_name for line in clusters)

    def preload_busybox_image(self) -> None:
        """Pre-pull busybox and load into Kind nodes to avoid rate limits during PVC helper jobs."""
        image = "docker.io/library/busybox:stable"
        self.logger.info(f"[Warmup] Pulling busybox image={image}")
        self.run(["docker", "pull", image])
        self.logger.info(f"[Warmup] Loading busybox into Kind name={self.cluster_name}")
        self.run(["kind", "load", "docker-image", image, "--name", self.cluster_name])

    def configure_macvlan_network(self) -> None:
        network_name = self.multus_network
        networks = self.run(["docker", "network", "ls", "--format", "{{.Name}}"], capture_output=True).stdout.splitlines()
        if network_name in networks:
            self.logger.info(f"[Network] Reusing Docker macvlan name={network_name}")
        else:
            self.logger.info(f"[Network] Creating Docker macvlan name={network_name} iface={self.multus_iface} " f"subnet={self.multus_subnet} gateway={self.multus_gateway} ip-range={self.multus_ip_range}")
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

        members_output = self.run(
            ["docker", "network", "inspect", network_name, "-f", "{{range .Containers}}{{.Name}} {{end}}"],
            check=False,
            capture_output=True,
        ).stdout
        already_attached = set(members_output.split()) if members_output else set()

        result = self.run(
            ["kind", "get", "nodes", "--name", self.cluster_name],
            check=False,
            capture_output=True,
        ).stdout
        if not result:
            raise BootstrapError(f"[Network] No nodes reported name={self.cluster_name} action=abort-macvlan-attachment")

        attached, already, failed = [], [], []
        for node in result.splitlines():
            node = node.strip()
            if not node or "control-plane" in node:
                continue
            if node in already_attached:
                already.append(node)
                continue
            completed = self.run(
                ["docker", "network", "connect", network_name, node],
                check=False,
            )
            if completed.returncode == 0:
                attached.append(node)
            else:
                failed.append(node)

        if attached:
            self.logger.info(f"[Network] Workers attached network={network_name} nodes={' '.join(attached)}")
        if already:
            self.logger.info(f"[Network] Workers already attached network={network_name} nodes={' '.join(already)}")
        if failed:
            raise BootstrapError(f"[Network] Failed to attach workers network={network_name} nodes={' '.join(failed)} " "detail=docker-network-connect-output")
        if not attached and not already and not failed:
            self.logger.info("[Network] No worker nodes eligible for macvlan attachment")

    def patch_kubeconfig_endpoint(self) -> None:
        if not self.advertise_host:
            return
        if not self.cluster_exists():
            raise BootstrapError("[Kubeconfig] Cannot patch endpoint; cluster does not exist")

        current_host, port = self.current_api_server_endpoint()
        if port is None:
            raise BootstrapError("[Kubeconfig] Missing API server port; cannot patch kubeconfig")
        if current_host == self.advertise_host:
            return

        new_server = f"https://{self.advertise_host}:{port}"
        self.logger.info(f"[Kubeconfig] Patching server endpoint server={new_server}")
        self.run(
            [
                "kubectl",
                "config",
                "set-cluster",
                self.kind_context,
                f"--server={new_server}",
            ]
        )
        return

    def current_api_server_endpoint(self) -> Tuple[Optional[str], Optional[int]]:
        raw = self.run(
            ["kubectl", "config", "view", "--raw", "-o", "json"],
            check=False,
            capture_output=True,
        ).stdout
        if not raw:
            return None, None

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None, None

        for cluster in data.get("clusters", []):
            if cluster.get("name") != self.kind_context:
                continue
            server = cluster.get("cluster", {}).get("server", "")
            return self.parse_host_port(server)
        return None, None

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
        current = self.run(
            [
                "kubectl",
                "-n",
                "kube-system",
                "get",
                "ds",
                "kindnet",
                "-o",
                "jsonpath={.spec.template.spec.containers[0].resources}",
            ],
            check=False,
            capture_output=True,
        ).stdout.strip()

        if not current or current in ("map[]", "{}"):
            self.logger.info("[Network] Skipping Kindnet patch reason=resources-already-removed")
            return

        self.logger.info("[Network] Removing Kindnet resource requests/limits")
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
            self.logger.warning("[Network] Failed to patch Kindnet reason=resources-maybe-absent")

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
        self.logger.info(f"[Kubernetes] Creating namespace name={namespace}")
        self.run(["kubectl", "create", "namespace", namespace])

    # -------------------------------------------------------- Secrets & ArgoCD
    def ensure_cluster_secrets_loaded(self) -> bool:
        if self.cluster_credentials_data is not None:
            return True
        if not self.cluster_credentials_sops_path.exists():
            raise BootstrapError(f"[Secrets] Missing cluster credentials file at {self.cluster_credentials_sops_path}")

        tmp = self.make_temp_file(suffix=".yaml")
        with tmp.open("w", encoding="utf-8") as handle:
            self.run(
                ["sops", "--decrypt", str(self.cluster_credentials_sops_path)],
                env=self.env,
                stdout=handle,
            )

        with tmp.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise BootstrapError(f"[Secrets] {self.cluster_credentials_sops_path} must be a Secret manifest")

        self.cluster_credentials_data = data
        self.decrypted_secrets_path = tmp
        return True

    def apply_cluster_secrets(self) -> None:
        self.ensure_cluster_secrets_loaded()
        assert self.decrypted_secrets_path is not None
        metadata = (self.cluster_credentials_data or {}).get("metadata") or {}
        namespace = str(metadata.get("namespace") or "platform-system")
        self.ensure_namespace_exists(namespace)
        self.logger.info("[Secrets] Applying cluster credentials secret=cluster-credentials decrypted=true")
        self.run(["kubectl", "apply", "-f", str(self.decrypted_secrets_path)])

    # ------------------------------------------------------------- Delete flow
    def teardown_cluster(self) -> None:
        if self.cluster_exists():
            self.logger.info(f"[Cluster] Deleting Kind cluster name={self.cluster_name}")
            self.run(["kind", "delete", "cluster", "--name", self.cluster_name], check=False)
        else:
            self.logger.info(f"[Cluster] Skipping delete reason=cluster-not-found name={self.cluster_name}")

        if self.multus_network:
            result = self.run(
                ["docker", "network", "rm", self.multus_network],
                check=False,
                capture_output=True,
            )
            if result.returncode == 0:
                self.logger.info(f"[Network] Removed Docker macvlan name={self.multus_network}")
            else:
                self.logger.info(f"[Network] Skipping removal reason=docker-network-not-found name={self.multus_network}")

    # --------------------------------------------------------------- Helpers
    def run(
        self,
        cmd: List[str],
        *,
        check: bool = True,
        capture_output: bool = False,
        env: Optional[Dict[str, str]] = None,
        stdout=None,
    ) -> subprocess.CompletedProcess[str]:
        merged_env = self.env.copy()
        if env:
            merged_env.update(env)
        return subprocess.run(
            cmd,
            check=check,
            text=True,
            capture_output=capture_output,
            env=merged_env,
            stdout=stdout,
        )

    @staticmethod
    def parse_host_port(server: str) -> Tuple[Optional[str], Optional[int]]:
        parsed = urlparse(server)
        if parsed.hostname or parsed.port:
            return parsed.hostname, parsed.port

        if ":" in server:
            host, port = server.rsplit(":", 1)
            if port.isdigit():
                return (host or None), int(port)
        return None, None


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
        bootstrapper.logger.exception(message)
        raise SystemExit(1) from exc
    finally:
        bootstrapper.cleanup()


if __name__ == "__main__":  # pragma: no cover
    main()
