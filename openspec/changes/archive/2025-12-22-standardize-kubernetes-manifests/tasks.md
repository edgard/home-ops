## Implementation Tasks

### 1. Audit and Catalog

- [x] 1.1 Generate list of all manifest files in `apps/*/manifests/`
- [x] 1.2 Identify files that don't follow naming convention
- [x] 1.3 Document current field ordering patterns
- [x] 1.4 Identify manifests with formatting issues (yamlfmt/yamllint violations)
- [x] 1.5 Create exemption list for vendor-provided CRDs

### 2. Standardize File Naming

- [x] 2.1 Review and validate file naming pattern for all ExternalSecrets
- [x] 2.2 Review and validate file naming pattern for all ConfigMaps
- [x] 2.3 Review and validate file naming pattern for all Certificates
- [x] 2.4 Review and validate file naming pattern for all Issuers
- [x] 2.5 Review and validate file naming pattern for all StorageClasses
- [x] 2.6 Review and validate file naming pattern for all CustomResourceDefinitions
- [x] 2.7 Review and validate file naming pattern for all other resource types
- [x] 2.8 Rename any files that don't match the pattern (excluding vendor CRDs)

### 3. Standardize Document Structure

- [x] 3.1 Ensure all manifests start with `---` document separator
- [x] 3.2 Verify single-resource-per-file pattern (except vendor CRDs)
- [x] 3.3 Ensure metadata.name matches filename pattern

### 4. Standardize Field Ordering

- [x] 4.1 Reorder top-level fields: apiVersion, kind, metadata, spec/data
- [x] 4.2 Reorder metadata fields: name, namespace, labels, annotations
- [x] 4.3 Apply ordering to all manifests in apps/argocd/
- [x] 4.4 Apply ordering to all manifests in apps/home-automation/
- [x] 4.5 Apply ordering to all manifests in apps/kube-system/
- [x] 4.6 Apply ordering to all manifests in apps/local-path-storage/
- [x] 4.7 Apply ordering to all manifests in apps/media/
- [x] 4.8 Apply ordering to all manifests in apps/platform-system/
- [x] 4.9 Apply ordering to all manifests in apps/selfhosted/
- [x] 4.10 Apply ordering to all manifests in argocd/namespaces/
- [x] 4.11 Apply ordering to all manifests in argocd/projects/

### 5. Apply Formatting Standards

- [x] 5.1 Run `task lint` to identify all formatting violations
- [x] 5.2 Apply yamlfmt to fix indentation and spacing issues
- [x] 5.3 Resolve any remaining yamllint violations
- [x] 5.4 Verify all manifests pass `task lint` without errors

### 6. Update Documentation

- [x] 6.1 Add "Resource Naming Conventions" section to openspec/project.md
- [x] 6.2 Document file naming pattern with examples
- [x] 6.3 Document field ordering conventions
- [x] 6.4 Add table of common resource types with naming patterns
- [x] 6.5 Document vendor CRD exemption policy

### 7. Validation and Testing

- [x] 7.1 Run `task lint` on entire codebase
- [x] 7.2 Verify Argo CD can parse all manifests (dry-run)
- [x] 7.3 Check git diff to ensure no unintended changes
- [x] 7.4 Validate all manifests with kubectl dry-run
- [x] 7.5 Review changes in at least 10 sample files across different resource types

## Notes

- Tasks 2-4 can be partially automated with scripts but require manual review
- Field ordering is best practice per Kubernetes documentation and community conventions
- Formatting should be handled by existing yamlfmt/yamllint tooling
- No functional changes - purely structural improvements
- Can be done incrementally by app group if preferred
- Git history will show renames clearly with `git log --follow`
