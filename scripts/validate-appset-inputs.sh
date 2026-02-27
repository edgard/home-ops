#!/usr/bin/env bash
set -euo pipefail

failed=0

tmp_seen_names=$(mktemp)
trap 'rm -f "$tmp_seen_names"' EXIT

for app in apps/*/*; do
  [ -d "$app" ] || continue

  app_file="$app/app.yaml"
  values_file="$app/values.yaml"

  if [ ! -f "$app_file" ]; then
    echo "Missing metadata file: $app_file"
    failed=1
    continue
  fi

  if [ ! -f "$values_file" ]; then
    echo "Missing values file: $values_file"
    failed=1
  fi

  category=${app#apps/}
  category=${category%%/*}
  app_name=${app##*/}
  generated_name="${category}-${app_name}"

  existing_path=$(awk -F'|' -v name="$generated_name" '$1 == name { print $2; exit }' "$tmp_seen_names")
  if [ -n "$existing_path" ]; then
    echo "Duplicate generated application name '$generated_name': $app and $existing_path"
    failed=1
  else
    echo "$generated_name|$app" >> "$tmp_seen_names"
  fi

  chart_repo=$(yq eval '.chart.repo // ""' "$app_file")
  chart_version=$(yq eval '.chart.version // ""' "$app_file")
  chart_name=$(yq eval '.chart.name // ""' "$app_file")
  sync_wave=$(yq eval '.sync.wave // ""' "$app_file")

  if [ -z "$chart_repo" ]; then
    echo "Missing chart.repo in $app_file"
    failed=1
  fi

  if [ -z "$chart_version" ]; then
    echo "Missing chart.version in $app_file"
    failed=1
  fi

  if [ -n "$chart_repo" ] && [[ "$chart_repo" != oci://* ]] && [ -z "$chart_name" ]; then
    echo "Missing chart.name for non-OCI chart repo in $app_file"
    failed=1
  fi

  if [ -n "$sync_wave" ] && ! [[ "$sync_wave" =~ ^-?[0-9]+$ ]]; then
    echo "sync.wave must be an integer string in $app_file"
    failed=1
  fi

  if [ "$(yq eval 'has("ignoreDifferences")' "$app_file")" = "true" ]; then
    ignore_type=$(yq eval '.ignoreDifferences | type' "$app_file")
    if [ "$ignore_type" != "!!seq" ]; then
      echo "ignoreDifferences must be a list in $app_file"
      failed=1
      continue
    fi

    ignore_count=$(yq eval '.ignoreDifferences | length' "$app_file")
    for ((i = 0; i < ignore_count; i++)); do
      has_group=$(yq eval ".ignoreDifferences[$i] | has(\"group\")" "$app_file")
      has_kind=$(yq eval ".ignoreDifferences[$i] | has(\"kind\")" "$app_file")

      if [ "$has_group" != "true" ] || [ "$has_kind" != "true" ]; then
        echo "ignoreDifferences[$i] must define both group and kind in $app_file"
        failed=1
      fi
    done
  fi
done

exit "$failed"
