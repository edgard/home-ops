# Validation and PR gate

Purpose: distinguish local checks, repository policy, and deployment evidence.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

`task lint` aggregates formatting, static analysis, wiki, workflow, Ansible,
Kubernetes, and Terraform validation. Source, metadata, raw manifest, and
rendered workload policy check repository contracts; Ansible tests exercise
role behavior and fixtures. CI runs focused targets as separate pull-request
jobs and collects their results in `Quality Gate`.

The [validation architecture decision](../decisions/validation-architecture.md)
explains the replacement of the former scripts directory. These checks prove
the committed configuration satisfies the tested contracts, not that a synced
application functions in the live cluster. Deployment acceptance requires
targeted runtime checks.

## Sources

- [Taskfile](../../../Taskfile.yaml)
- [CI workflow](../../../.github/workflows/ci.yml)
- [Kubernetes validation playbook](../../../ansible/playbooks/validate-kubernetes.yml)
- [Wiki validation playbook](../../../ansible/playbooks/validate-wiki.yml)
- [Policy tree](../../../policy)

## Related pages

- [GitOps delivery](gitops-delivery.md)
- [Agent workflow](../agent-workflow.md)
