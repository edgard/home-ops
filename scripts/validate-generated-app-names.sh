#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="${REPO_ROOT:-$(cd -- "${script_dir}/.." && pwd)}"
apps_root="${APPS_ROOT:-${repo_root}/apps}"
failed=0
tmp_seen_names="$(mktemp)"

cleanup() {
  rm -f "$tmp_seen_names"
}

trap cleanup EXIT

for app in "${apps_root}"/*/*; do
  [ -d "$app" ] || continue

  category="${app#"${apps_root}/"}"
  category="${category%%/*}"
  app_name="${app##*/}"
  generated_name="${category}-${app_name}"
  existing_path=$(awk -F'|' -v name="$generated_name" '$1 == name { print $2; exit }' "$tmp_seen_names")

  if [ -n "$existing_path" ]; then
    echo "Duplicate generated application name '$generated_name': $app and $existing_path"
    failed=1
  else
    echo "$generated_name|$app" >> "$tmp_seen_names"
  fi
done

exit "$failed"
