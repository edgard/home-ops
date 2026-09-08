#!/usr/bin/env bash
# Install the test-only MetricsQL evaluator. It runs an isolated database only during tests.
set -euo pipefail

# renovate: datasource=github-releases depName=VictoriaMetrics/VictoriaMetrics
version="1.151.0"
destination="${1:?Usage: install-vmalert-tool.sh DESTINATION}"

if [ -x "$destination/vmalert-tool" ] && "$destination/vmalert-tool" -version 2>&1 | head -1 | grep -Fq "v${version}"; then
  exit 0
fi

case "$(uname -s)" in
  Darwin) os=darwin ;;
  Linux) os=linux ;;
  *) echo "Unsupported vmalert-tool platform" >&2; exit 1 ;;
esac
case "$(uname -m)" in
  arm64 | aarch64) arch=arm64 ;;
  x86_64) arch=amd64 ;;
  *) echo "Unsupported vmalert-tool architecture" >&2; exit 1 ;;
esac

archive="vmutils-${os}-${arch}-v${version}.tar.gz"
url="https://github.com/VictoriaMetrics/VictoriaMetrics/releases/download/v${version}"
temp_dir="$(mktemp -d)"
trap 'rm -rf "$temp_dir"' EXIT
curl --retry 5 --retry-all-errors --connect-timeout 15 --max-time 300 -fsSL "$url/$archive" -o "$temp_dir/$archive"
curl --retry 5 --retry-all-errors --connect-timeout 15 --max-time 60 -fsSL "$url/${archive%.tar.gz}_checksums.txt" -o "$temp_dir/checksums.txt"
grep "  ${archive}$" "$temp_dir/checksums.txt" | (cd "$temp_dir" && shasum -a 256 --check --status)
tar -xzf "$temp_dir/$archive" -C "$temp_dir" vmalert-tool-prod
mkdir -p "$destination"
install -m 755 "$temp_dir/vmalert-tool-prod" "$destination/vmalert-tool"
