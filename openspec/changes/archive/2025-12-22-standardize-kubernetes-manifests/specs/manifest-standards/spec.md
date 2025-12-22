## ADDED Requirements

### Requirement: File Naming Convention

All Kubernetes manifest files in the project SHALL follow a consistent naming pattern to enable predictable discovery and identification.

#### Scenario: Standard manifest file naming

- **WHEN** creating a new Kubernetes manifest file
- **THEN** the file MUST be named following the pattern `{app}-{descriptor}.{kind}.yaml` where:
  - `{app}` is the application name (kebab-case)
  - `{descriptor}` is an optional descriptor providing context (kebab-case, e.g., "credentials", "config", "wildcard")
  - `{kind}` is the Kubernetes resource kind in lowercase (e.g., "externalsecret", "configmap", "certificate")

#### Scenario: Vendor-provided CRD exemption

- **WHEN** including vendor-provided CRD manifests (e.g., Gateway API CRDs)
- **THEN** the original filename MAY be preserved as-is
- **AND** multi-document YAML files containing multiple CRDs are acceptable

#### Scenario: File name matches resource name

- **WHEN** the manifest file is named `{app}-{descriptor}.{kind}.yaml`
- **THEN** the resource's `metadata.name` SHOULD match `{app}-{descriptor}` (without the kind suffix)

### Requirement: YAML Document Structure

All manifest files SHALL use consistent YAML formatting to ensure uniform parsing and readability.

#### Scenario: Document separator placement

- **WHEN** creating a manifest file
- **THEN** the file MUST start with the YAML document separator `---` on the first line
- **AND** single-resource manifests MUST contain exactly one document

#### Scenario: Multi-document file restriction

- **WHEN** creating user-authored manifests
- **THEN** each manifest file SHOULD contain only one Kubernetes resource
- **AND** multi-document files are only acceptable for vendor-provided resources

### Requirement: Field Ordering Convention

Kubernetes resource fields SHALL follow a consistent top-level ordering to improve readability and maintainability.

#### Scenario: Standard field order

- **WHEN** writing a Kubernetes manifest
- **THEN** top-level fields MUST appear in the following order:
  1. `apiVersion`
  2. `kind`
  3. `metadata`
  4. `spec` (if present)
  5. `data` (for ConfigMaps/Secrets)
  6. Other fields as needed

#### Scenario: Metadata field order

- **WHEN** defining the `metadata` section
- **THEN** fields SHOULD appear in the following order:
  1. `name`
  2. `namespace` (if namespaced)
  3. `labels` (if present)
  4. `annotations` (if present)
  5. Other metadata fields

### Requirement: YAML Formatting Standards

All manifests SHALL adhere to project-defined YAML formatting rules to ensure consistency across the codebase.

#### Scenario: Indentation and spacing

- **WHEN** formatting YAML manifests
- **THEN** indentation MUST use 2 spaces (no tabs)
- **AND** formatting MUST comply with `.yamlfmt` configuration
- **AND** linting MUST pass `.yamllint` rules

#### Scenario: Enforcement via tooling

- **WHEN** committing manifest changes
- **THEN** the `task lint` command MUST pass without errors
- **AND** yamlfmt and yamllint checks MUST succeed

### Requirement: Manifest Location Convention

Kubernetes manifests SHALL be organized in a consistent directory structure based on their purpose.

#### Scenario: App-specific manifests location

- **WHEN** creating manifests for an application
- **THEN** user-authored manifests MUST be placed in `apps/<group>/<app>/manifests/`
- **AND** the manifests directory MUST only contain Kubernetes resource YAML files

#### Scenario: Infrastructure manifests location

- **WHEN** creating namespace or project manifests for Argo CD
- **THEN** namespace manifests MUST be placed in `argocd/namespaces/`
- **AND** project manifests MUST be placed in `argocd/projects/`
- **AND** follow the same naming pattern with `.namespace.yaml` or `.appproject.yaml` suffix

### Requirement: Documentation of Standards

The manifest standards SHALL be documented in the project to ensure all contributors follow the same conventions.

#### Scenario: Project.md documentation

- **WHEN** the standardization is complete
- **THEN** `openspec/project.md` MUST include a "Resource Naming Conventions" section
- **AND** the section MUST document the file naming pattern with examples
- **AND** the section MUST list common resource types and their naming patterns

#### Scenario: Examples for common resource types

- **WHEN** documenting naming conventions
- **THEN** examples MUST be provided for at least:
  - ExternalSecret: `{app}-[{descriptor}-]credentials.externalsecret.yaml`
  - ConfigMap: `{app}-{descriptor}.configmap.yaml`
  - Certificate: `{app}-{descriptor}.certificate.yaml`
  - Issuer: `{app}-issuer-{env}.issuer.yaml`
  - StorageClass: `{name}.storageclass.yaml`
  - CustomResourceDefinition: `{plural}.{group}.customresourcedefinition.yaml`
