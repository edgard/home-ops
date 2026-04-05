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
