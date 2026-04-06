#!/usr/bin/env bats

@test "renovate operator job uses provider config instead of legacy platform env vars" {
  manifest="${BATS_TEST_DIRNAME}/../apps/selfhosted/renovate-operator/manifests/renovate-operator-home-ops.renovatejob.yaml"

  run grep -F "provider:" "$manifest"
  [ "$status" -eq 0 ]

  run grep -F "name: github" "$manifest"
  [ "$status" -eq 0 ]

  run grep -F "endpoint: https://api.github.com/" "$manifest"
  [ "$status" -eq 0 ]

  run grep -E '^[[:space:]]*- name: RENOVATE_PLATFORM$' "$manifest"
  [ "$status" -eq 1 ]

  run grep -E '^[[:space:]]*- name: RENOVATE_ENDPOINT$' "$manifest"
  [ "$status" -eq 1 ]
}

@test "renovate non-major updates use pr automerge and do not skip checks" {
  config="${BATS_TEST_DIRNAME}/../.renovaterc.json5"

  run grep -F 'description: "Auto-merge non-major updates"' "$config"
  [ "$status" -eq 0 ]

  run grep -F 'automergeType: "pr"' "$config"
  [ "$status" -eq 0 ]

  run grep -F 'ignoreTests: true' "$config"
  [ "$status" -eq 1 ]
}

@test "renovate operator job sets an explicit git author and does not use platform commits" {
  manifest="${BATS_TEST_DIRNAME}/../apps/selfhosted/renovate-operator/manifests/renovate-operator-home-ops.renovatejob.yaml"

  run grep -E '^[[:space:]]*- name: RENOVATE_GIT_AUTHOR$' "$manifest"
  [ "$status" -eq 0 ]

  run grep -F 'value: "Renovate Bot <renovate@edgard.org>"' "$manifest"
  [ "$status" -eq 0 ]

  run grep -E '^[[:space:]]*- name: RENOVATE_PLATFORM_COMMIT$' "$manifest"
  [ "$status" -eq 1 ]
}

@test "renovate operator job uses v4 discoveryFilters and not legacy discoveryFilter" {
  manifest="${BATS_TEST_DIRNAME}/../apps/selfhosted/renovate-operator/manifests/renovate-operator-home-ops.renovatejob.yaml"

  run grep -E '^[[:space:]]*discoveryFilters:$' "$manifest"
  [ "$status" -eq 0 ]

  run grep -E '^[[:space:]]*-[[:space:]]+edgard/home-ops$' "$manifest"
  [ "$status" -eq 0 ]

  run grep -E '^[[:space:]]*discoveryFilter:' "$manifest"
  [ "$status" -eq 1 ]
}

@test "renovate config tracks tuppr upgrade manifests and CI tool inputs" {
  config="${BATS_TEST_DIRNAME}/../.renovaterc.json5"

  run grep -F 'description: "Tuppr upgrade versions"' "$config"
  [ "$status" -eq 0 ]

  run grep -F '/^apps\\/platform-system\\/tuppr\\/manifests\\/.*\\.(talosupgrade|kubernetesupgrade)\\.ya?ml$/' "$config"
  [ "$status" -eq 0 ]

  run grep -F 'description: "CI tool versions in GitHub Actions workflow"' "$config"
  [ "$status" -eq 0 ]

  run grep -F '/^\\.github\\/workflows\\/ci\\.ya?ml$/' "$config"
  [ "$status" -eq 0 ]

  run grep -F '(?<currentValue>[0-9.]+)' "$config"
  [ "$status" -eq 0 ]
}

@test "external-dns values declare the main image repository explicitly" {
  values="${BATS_TEST_DIRNAME}/../apps/platform-system/external-dns/values.yaml"

  run grep -F 'repository: registry.k8s.io/external-dns/external-dns' "$values"
  [ "$status" -eq 0 ]
}

@test "renovate config tracks image repository and tag pairs in app values files" {
  config="${BATS_TEST_DIRNAME}/../.renovaterc.json5"
  values="${BATS_TEST_DIRNAME}/../apps/platform-system/external-dns/values.yaml"

  run grep -F 'description: "Container images in app values files"' "$config"
  [ "$status" -eq 0 ]

  run grep -F '/^apps\\/[^\\/]+\\/[^\\/]+\\/values\\.ya?ml$/' "$config"
  [ "$status" -eq 0 ]

  run grep -F 'repository:\\s*(?<depName>' "$config"
  [ "$status" -eq 0 ]

  run grep -F 'tag:\\s*[' "$config"
  [ "$status" -eq 0 ]

  run grep -F 'repository: registry.k8s.io/external-dns/external-dns' "$values"
  [ "$status" -eq 0 ]

  run grep -F 'repository: ghcr.io/kashalls/external-dns-unifi-webhook' "$values"
  [ "$status" -eq 0 ]
}

@test "renovate config includes migration and GitHub Action digest pinning helpers" {
  config="${BATS_TEST_DIRNAME}/../.renovaterc.json5"

  run grep -F '":configMigration"' "$config"
  [ "$status" -eq 0 ]

  run grep -F '"helpers:pinGitHubActionDigestsToSemver"' "$config"
  [ "$status" -eq 0 ]
}
