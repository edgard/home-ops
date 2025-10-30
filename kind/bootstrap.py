#!/usr/bin/env python3
import argparse
import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

# User-configurable defaults
DEFAULT_KUBECONFIG_PATH = Path.home() / ".kube/config"
MULTUS_PARENT_IFACE = "br0"
MULTUS_PARENT_SUBNET = "192.168.1.0/24"
MULTUS_PARENT_GATEWAY = "192.168.1.1"
MULTUS_PARENT_IP_RANGE = "192.168.1.240/29"

# Internal constants derived from configuration
REPO_ROOT = Path(__file__).resolve().parent.parent
KIND_CONFIG_PATH = REPO_ROOT / "kind" / "cluster-config.yaml"
SOPS_AGE_KEY_PATH = REPO_ROOT / ".sops.agekey"
GIT_CREDENTIALS_PATH = REPO_ROOT / ".git-credentials"


def log(message: str) -> None:
  print(f"\n[{datetime.now():%H:%M:%S}] {message}")


def require(command: str) -> None:
  if shutil.which(command) is None:
    print(f"fatal: {command} is required", file=sys.stderr)
    sys.exit(1)


def run(cmd, *, env=None, capture=False, check=True, input=None) -> subprocess.CompletedProcess:
  return subprocess.run(
    cmd,
    env=env,
    check=check,
    text=True,
    capture_output=capture,
    input=input,
  )


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Bootstrap the Kind-based homelab cluster or destroy it.")
  parser.add_argument(
    "-d",
    "--destroy",
    action="store_true",
    help="Destroy the Kind cluster instead of creating and bootstrapping it.",
  )
  return parser.parse_args()


def parse_remote_host(endpoint: str) -> str:
  if not endpoint:
    return ""
  if endpoint.startswith(("unix://", "npipe://")):
    return ""
  if endpoint.startswith("tcp://"):
    host = endpoint[len("tcp://") :]
    return host.split(":", 1)[0]
  if endpoint.startswith("ssh://"):
    host = endpoint[len("ssh://") :]
    host = host.split("@", 1)[-1]
    return host.split(":", 1)[0]
  return ""


def patch_kind_config(original_text: str, address: str, san_host: str) -> Tuple[str, Dict[str, bool]]:
  lines = original_text.splitlines()
  changed = {"address": False, "san": False}

  if address:
    desired_line = f"  apiServerAddress: {address}"
    for idx, line in enumerate(lines):
      if line.startswith("  apiServerAddress:"):
        if line != desired_line:
          lines[idx] = desired_line
          changed["address"] = True
        break
    else:
      for idx, line in enumerate(lines):
        if line.startswith("  serviceSubnet:"):
          lines.insert(idx + 1, desired_line)
          changed["address"] = True
          break
      else:
        lines.append(desired_line)
        changed["address"] = True

  if san_host:
    desired_line = f"            - {san_host}"
    if desired_line not in lines:
      block_index = next((i for i, line in enumerate(lines) if line.strip() == "certSANs:"), None)
      if block_index is not None:
        insert_at = block_index + 1
        while insert_at < len(lines) and lines[insert_at].startswith("            - "):
          insert_at += 1
        lines.insert(insert_at, desired_line)
        changed["san"] = True
      else:
        for idx, line in enumerate(lines):
          if line.strip() == "enable-admission-plugins: NodeRestriction":
            block = [
              "          certSANs:",
              "            - localhost",
              "            - 127.0.0.1",
              desired_line,
            ]
            lines[idx + 1 : idx + 1] = block
            changed["san"] = True
            break

  if any(changed.values()):
    return "\n".join(lines) + "\n", changed
  return original_text, changed


@dataclass(frozen=True)
class BootstrapSettings:
  repo_root: Path = REPO_ROOT
  kind_config: Path = KIND_CONFIG_PATH
  kubeconfig: Path = DEFAULT_KUBECONFIG_PATH
  sops_age_key: Path = SOPS_AGE_KEY_PATH
  git_credentials: Path = GIT_CREDENTIALS_PATH
  cluster_name: str = ""
  docker_context: str = ""
  multus_network: str = ""

  def __post_init__(self) -> None:
    name = load_cluster_name(self.kind_config)
    object.__setattr__(self, "cluster_name", name)
    object.__setattr__(self, "docker_context", f"kind-{name}")
    object.__setattr__(self, "multus_network", f"kind-{name}-net")


@contextlib.contextmanager
def switch_docker_context(target: str) -> None:
  original = run(["docker", "context", "show"], capture=True).stdout.strip()
  if original != target:
    log(f"Switching docker context to {target}")
    run(["docker", "context", "use", target])
  try:
    yield original
  finally:
    if original != target:
      run(["docker", "context", "use", original], check=False)


@contextlib.contextmanager
def temporary_kind_config(config: Path, bind_address: str, san_host: str) -> Tuple[Path, Dict[str, bool]]:
  text = config.read_text()
  patched, changes = patch_kind_config(text, bind_address, san_host)
  if any(changes.values()):
    with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
      tmp.write(patched)
      temp_path = Path(tmp.name)
    try:
      yield temp_path, changes
    finally:
      temp_path.unlink(missing_ok=True)
  else:
    yield config, changes


def list_kind_clusters() -> set[str]:
  result = run(["kind", "get", "clusters"], capture=True, check=False)
  if result.returncode != 0:
    return set()
  return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def cluster_exists(name: str) -> bool:
  return name in list_kind_clusters()


def inspect_docker_host(context: str) -> str:
  result = run(
    [
      "docker",
      "context",
      "inspect",
      context,
      "--format",
      "{{ if .Endpoints.docker.Host }}{{ .Endpoints.docker.Host }}{{ end }}",
    ],
    capture=True,
    check=False,
  )
  return result.stdout.strip() if result.returncode == 0 else ""


def list_docker_contexts() -> set[str]:
  result = run(["docker", "context", "ls", "--format", "{{.Name}}"], capture=True, check=False)
  if result.returncode != 0:
    return set()
  return {line.strip() for line in result.stdout.splitlines() if line.strip()}

def ensure_macvlan_network(
  name: str,
  parent_iface: str,
  subnet: str,
  gateway: str,
  ip_range: str,
) -> None:
  existing = run(["docker", "network", "ls", "--format", "{{.Name}}"], capture=True).stdout.splitlines()
  if name not in existing:
    log(
      f"Creating docker macvlan network {name} on parent {parent_iface} "
      f"(subnet {subnet}, ip-range {ip_range})"
    )
    run(
      [
        "docker",
        "network",
        "create",
        "-d",
        "macvlan",
        "--subnet",
        subnet,
        "--gateway",
        gateway,
        "--ip-range",
        ip_range,
        "-o",
        f"parent={parent_iface}",
        name,
      ]
    )
    return

  log(f"Reusing existing docker network {name}")


def connect_workers_to_network(cluster_name: str, network_name: str) -> None:
  nodes = run(["kind", "get", "nodes", "--name", cluster_name], capture=True, check=False)
  if nodes.returncode != 0:
    log(f"Skipping network attach; no nodes found for cluster {cluster_name}")
    return

  for node in (line.strip() for line in nodes.stdout.splitlines() if line.strip()):
    if "control-plane" in node:
      log(f"Skipping macvlan attach for control-plane node {node}")
      continue

    networks = run(
      ["docker", "inspect", "--format", "{{ range $k, $_ := .NetworkSettings.Networks }}{{ $k }} {{ end }}", node],
      capture=True,
    ).stdout.split()

    if network_name in networks:
      log(f"Node {node} already connected to {network_name}")
      continue

    log(f"Connecting node {node} to docker network {network_name}")
    run(["docker", "network", "connect", network_name, node])


def destroy_cluster(
  cluster_name: str,
  macvlan_network: Optional[str] = None,
) -> None:
  if not cluster_exists(cluster_name):
    log(f"No kind cluster named {cluster_name} found; nothing to destroy")
  else:
    log(f"Deleting kind cluster {cluster_name}")
    run(["kind", "delete", "cluster", "--name", cluster_name], check=False)
    log(f"Destroyed kind cluster {cluster_name}")

  if macvlan_network:
    existing = run(["docker", "network", "ls", "--format", "{{.Name}}"], capture=True).stdout.splitlines()
    if macvlan_network in existing:
      log(f"Removing docker macvlan network {macvlan_network}")
      run(["docker", "network", "rm", macvlan_network], check=False)
    else:
      log(f"No docker network named {macvlan_network} found; nothing to remove")


def load_cluster_name(config_path: Path) -> str:
  try:
    for line in config_path.read_text().splitlines():
      stripped = line.strip()
      if not stripped or stripped.startswith("#"):
        continue
      if line.startswith("name:"):
        _, _, value = stripped.partition(":")
        name = value.strip()
        if name:
          return name
  except FileNotFoundError:
    pass
  raise RuntimeError(f"Kind config {config_path} does not define a cluster name")



def main() -> None:
  args = parse_args()
  settings = BootstrapSettings()

  required_commands = ["docker", "kind"]
  if not args.destroy:
    required_commands.extend(["kubectl", "flux"])
  for command in required_commands:
    require(command)

  command_env = os.environ.copy()
  command_env["KUBECONFIG"] = str(settings.kubeconfig)

  available_contexts = list_docker_contexts()
  if settings.docker_context not in available_contexts:
    raise SystemExit(f"fatal: docker context '{settings.docker_context}' not found. Create it before running bootstrap.")

  with switch_docker_context(settings.docker_context):
    if args.destroy:
      destroy_cluster(settings.cluster_name, settings.multus_network)
      return

    remote_host = parse_remote_host(inspect_docker_host(settings.docker_context))
    if remote_host in {"127.0.0.1", "localhost"}:
      remote_host = ""

    bind_address = "0.0.0.0" if remote_host else ""
    advertise_host = remote_host

    with temporary_kind_config(settings.kind_config, bind_address, advertise_host) as (config_path, changes):
      if changes["address"]:
        log(f"Using temporary Kind config with apiServerAddress={bind_address}")
      if changes["san"] and advertise_host:
        log(f"Adding {advertise_host} to kube-apiserver certificate SANs")

      config_differs = any(changes.values())
      existing_cluster = cluster_exists(settings.cluster_name)

      ensure_macvlan_network(
        settings.multus_network,
        MULTUS_PARENT_IFACE,
        MULTUS_PARENT_SUBNET,
        MULTUS_PARENT_GATEWAY,
        MULTUS_PARENT_IP_RANGE,
      )

      if existing_cluster and config_differs:
        log(
          "Cluster {0} already exists; rerun with --destroy to apply updated API server exposure settings".format(
            settings.cluster_name
          )
        )

      if not existing_cluster:
        log(f"Creating kind cluster {settings.cluster_name}")
        run(
          [
            "kind",
            "create",
            "cluster",
            "--config",
            str(config_path),
          ],
          env=command_env,
        )

    connect_workers_to_network(settings.cluster_name, settings.multus_network)

    cluster_context = f"kind-{settings.cluster_name}"
    if advertise_host:
      result = run(
        ["kubectl", "config", "view", "--raw", "-o", f"jsonpath={{.clusters[?(@.name=='{cluster_context}')].cluster.server}}"],
        capture=True,
        env=command_env,
        check=False,
      )
      if result.returncode == 0:
        server = result.stdout.strip()
        if server.startswith("https://"):
          host_port = server[len("https://") :]
          host, _, port_part = host_port.partition(":")
          if host and port_part and host != advertise_host:
            log(f"Patching kubeconfig server endpoint to https://{advertise_host}:{port_part}")
            run(
              ["kubectl", "config", "set-cluster", cluster_context, f"--server=https://{advertise_host}:{port_part}"],
              env=command_env,
            )

    log("Waiting for nodes to become Ready")
    run(["kubectl", "wait", "--for=condition=Ready", "node", "--all", "--timeout=180s"], env=command_env)

    log("Running flux check --pre")
    run(["flux", "check", "--pre"], env=command_env)

    log("Installing Flux controllers")
    run(
      [
        "flux",
        "install",
        "--namespace",
        "flux-system",
        "--components-extra=image-reflector-controller,image-automation-controller",
        "--watch-all-namespaces",
      ],
      env=command_env,
    )

    log("Verifying Flux installation")
    run(["flux", "check"], env=command_env)

    if settings.sops_age_key.exists():
      log(f"Applying flux-system/sops-age secret from {settings.sops_age_key}")
      manifest = run(
        [
          "kubectl",
          "-n",
          "flux-system",
          "create",
          "secret",
          "generic",
          "sops-age",
          f"--from-file=age.agekey={settings.sops_age_key}",
          "--dry-run=client",
          "-o",
          "yaml",
        ],
        env=command_env,
        capture=True,
      ).stdout
      run(["kubectl", "apply", "-f", "-"], env=command_env, input=manifest)
    else:
      log(f"Skipping SOPS secret creation (generate {settings.sops_age_key} via make sops-key-generate)")

    git_username = ""
    git_pat = ""
    if settings.git_credentials.exists():
      log(f"Loading Git credentials from {settings.git_credentials}")
      for line in settings.git_credentials.read_text().splitlines():
        if line.startswith("username="):
          git_username = line.split("=", 1)[1].strip()
        elif line.startswith("password="):
          git_pat = line.split("=", 1)[1].strip()

    if git_username and git_pat:
      log("Applying flux-system/home-ops-git secret for Git push")
      manifest = run(
        [
          "kubectl",
          "-n",
          "flux-system",
          "create",
          "secret",
          "generic",
          "home-ops-git",
          f"--from-literal=username={git_username}",
          f"--from-literal=password={git_pat}",
          "--dry-run=client",
          "-o",
          "yaml",
        ],
        env=command_env,
        capture=True,
      ).stdout
      run(["kubectl", "apply", "-f", "-"], env=command_env, input=manifest)
    else:
      log(f"Skipping Git credentials secret (populate {settings.git_credentials} with username= / password= lines)")

    log("Applying cluster sync manifests")
    run(
      [
        "kubectl",
        "apply",
        "-k",
        str(settings.repo_root / "kubernetes" / "clusters" / "homelab" / "flux-system"),
      ],
      env=command_env,
    )

    log("Triggering initial Flux reconciliation")
    run(
      ["flux", "reconcile", "source", "git", "home-ops", "--namespace", "flux-system"],
      env=command_env,
    )
    run(
      ["flux", "reconcile", "kustomization", "home-ops", "--namespace", "flux-system"],
      env=command_env,
    )

    log(f"Bootstrap complete. kubectl context is {cluster_context}.")


if __name__ == "__main__":
  main()
