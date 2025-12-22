# Change: Standardize Kubernetes Manifest Format and Structure

## Why

Currently, Kubernetes manifests across the project follow similar but not identical patterns, leading to maintenance friction and cognitive overhead when working across different apps. Inconsistencies exist in file naming, field ordering, formatting, and structural patterns. Standardizing these manifests will improve maintainability, reduce errors, and make the codebase easier to navigate and understand.

## What Changes

- Enforce consistent file naming pattern: `{app}-{descriptor}.{kind}.yaml`
- Standardize YAML document structure with `---` separator at start
- Establish consistent field ordering: `apiVersion`, `kind`, `metadata`, `spec`, `data`
- Normalize metadata structure: `name`, `namespace`, `labels` (when present), `annotations` (when present)
- Ensure consistent indentation (2 spaces) and formatting via existing `.yamlfmt` and `.yamllint` configs
- Document manifest naming conventions in project.md
- Apply standards to all user-created manifests (excludes vendor-provided CRDs like Gateway API)

## Impact

- Affected specs: `manifest-standards` (new capability)
- Affected code: All YAML manifests in `apps/*/manifests/` directories (~45 files)
- No breaking changes - purely structural/formatting improvements
- Requires one-time bulk reformatting pass across all manifests
- Future manifests must follow documented standards
