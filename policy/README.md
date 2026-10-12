# Repository policy and behavior tests

Policy decides whether repository configuration is allowed. Tests exercise the
behavior of policies, inventory adapters, Ansible roles, and native commands.

| Layer | Owns | Runner |
| --- | --- | --- |
| `repository/` | Task interfaces, SecretSpec ownership, infrastructure inputs, Talos target compatibility, and validation wiring | `task lint:repository` |
| `ansible/` | Static role task safety, inherited safeguards, operation ordering, credential mappings, and restore contracts | `task lint:ansible` |
| `metadata/` | App discovery metadata, chart declarations, sync waves, and generated names | `task lint:kubernetes` |
| `source/` | Helm values, source conventions, and cross-file application configuration | `task lint:kubernetes` |
| `kubernetes/` | Raw/rendered resource guardrails and aggregate Gatus route coverage | `task lint:kubernetes` |

Ansible validation roles collect and normalize policy inputs and invoke Conftest.
Adapters may parse TOML, JSON5, HCL, embedded YAML, and inherited task context.
They must reject parsing failures; they do not decide whether the configuration
satisfies a domain rule. File discovery and required inventory inputs remain
explicit so missing sources cannot silently remove a policy's scope.
The repository adapter reads tracked Terraform source files, excluding generated
and private local files. Stage new Terraform files before running the gate so
their configuration is included.

Some checks belong to native lint tools: Git decides tracked/ignored credential
artifacts, the wiki checker validates Markdown links and structure, kubeconform
validates API schemas, and Pluto checks deprecations. These are validation runners,
not application behavior tests. Ansible owns their orchestration.

## Regression coverage

Each policy's `*_test.rego` files exercise valid and invalid configurations.
Behavior fixtures under `ansible/tests/` exercise real role execution against
disposable files, synthetic APIs, and controlled command boundaries. Python tests
under `ansible/tests/unit/` include parser units and isolated integration fixtures.
Inventory/runner integration tests may mutate source files and assert that the
actual policy runner rejects unsafe inputs; the policy itself remains in Rego.

Keep installation/checksum handling, filesystem cleanup, command construction,
restore planning, check-mode effects, token rollback, safe diagnostics, parser
behavior, and OpenTofu sensitivity tests in the behavior suite. Keep assertions
about committed settings and task structure in policy. Do not duplicate a rule in
both places unless the test exercises a separate execution or normalization
boundary.

Runtime assertions in operator roles still validate the inputs and live state of
an operation. Offline source policy supplements those guards; it cannot replace
runtime checks or establish deployment health.

Application-specific rules apply to discovered apps. Missing wiring within an
app is rejected, while intentional removal of an entire app is reviewed as a
GitOps change rather than blocked by a fixed list of required app directories.

`task lint` runs every layer and fixture suite. CI runs the same focused targets;
the Ansible job includes `lint:repository`, and Quality Gate aggregates all jobs.
