# Restic Live Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Ansible-driven restic restore tasks that infer Argo-managed app PVCs and workloads from live Argo CD and Kubernetes state, with `snapshot` defaulting to `latest` and a `restore-all` mode.

**Architecture:** A new `restic_restore` role builds a restore plan from live Argo CD `Application.status.resources`, live PVCs, and live scalable workloads. The role defaults to plan-only output; destructive execution requires `confirm_restore=true`. Taskfile wrappers expose single-app and all-app restore workflows.

**Tech Stack:** Ansible, `kubernetes.core.k8s_info`, `kubernetes.core.k8s`, `kubernetes.core.k8s_json_patch`, `kubernetes.core.k8s_exec`, `kubernetes.core.k8s_scale`, Argo CD Application CRs, Kubernetes PVC and workload specs, restic restore job.

---

### Task 1: Add Restore Role Contract Tests

**Files:**
- Create: `ansible/tests/restic-restore.yml`
- Modify: `Taskfile.yaml`

- [ ] **Step 1: Write the failing plan tests**

Create `ansible/tests/restic-restore.yml`:

```yaml
---
- name: Validate restic restore plan construction
  hosts: localhost
  gather_facts: false
  vars:
    restic_restore_test_mode: true
    restic_restore_snapshot: ""
    restic_restore_applications:
      - metadata:
          name: cert-data
        spec:
          destination:
            namespace: platform-system
        status:
          resources:
            - kind: PersistentVolumeClaim
              namespace: platform-system
              name: cert-data
            - kind: Deployment
              namespace: platform-system
              name: cert-data
      - metadata:
          name: paperless
        spec:
          destination:
            namespace: selfhosted
        status:
          resources:
            - kind: PersistentVolumeClaim
              namespace: selfhosted
              name: paperless
            - kind: Deployment
              namespace: selfhosted
              name: paperless-main
            - kind: Deployment
              namespace: selfhosted
              name: paperless-gpt
      - metadata:
          name: restic
        spec:
          destination:
            namespace: selfhosted
        status:
          resources:
            - kind: PersistentVolumeClaim
              namespace: selfhosted
              name: restic-repo
      - metadata:
          name: nfs-provisioner
        spec:
          destination:
            namespace: kube-system
        status:
          resources:
            - kind: PersistentVolumeClaim
              namespace: media
              name: media
    restic_restore_pvcs:
      - metadata:
          namespace: platform-system
          name: cert-data
        spec:
          storageClassName: nfs-fast
      - metadata:
          namespace: selfhosted
          name: paperless
        spec:
          storageClassName: nfs-fast
      - metadata:
          namespace: selfhosted
          name: restic-repo
        spec:
          storageClassName: ""
      - metadata:
          namespace: media
          name: media
        spec:
          storageClassName: ""
    restic_restore_workloads:
      - kind: Deployment
        metadata:
          namespace: platform-system
          name: cert-data
        spec:
          replicas: 1
          template:
            spec:
              volumes:
                - name: data
                  persistentVolumeClaim:
                    claimName: cert-data
      - kind: Deployment
        metadata:
          namespace: selfhosted
          name: paperless-main
        spec:
          replicas: 1
          template:
            spec:
              volumes:
                - name: data
                  persistentVolumeClaim:
                    claimName: paperless
      - kind: Deployment
        metadata:
          namespace: selfhosted
          name: paperless-gpt
        spec:
          replicas: 1
          template:
            spec:
              volumes: []

  tasks:
    - name: Build single app restore plan
      ansible.builtin.include_role:
        name: restic_restore
      vars:
        restic_restore_mode: app
        restic_restore_app: paperless

    - name: Assert single app plan defaults snapshot to latest
      ansible.builtin.assert:
        that:
          - restic_restore_effective_snapshot == "latest"
          - restic_restore_plan | length == 1
          - restic_restore_plan[0].app == "paperless"
          - restic_restore_plan[0].namespace == "selfhosted"
          - restic_restore_plan[0].pvc_paths == ["/data/appdata/selfhosted/paperless"]
          - restic_restore_plan[0].restore_paths == ["/restore/data/appdata/selfhosted/paperless"]
          - 'restic_restore_plan[0].workloads == [{"api_version": "apps/v1", "kind": "Deployment", "namespace": "selfhosted", "name": "paperless-gpt", "replicas": 1}, {"api_version": "apps/v1", "kind": "Deployment", "namespace": "selfhosted", "name": "paperless-main", "replicas": 1}]'

    - name: Build all app restore plan
      ansible.builtin.include_role:
        name: restic_restore
      vars:
        restic_restore_mode: all

    - name: Assert restore-all includes platform appdata and excludes shared media and restic repo PVCs
      ansible.builtin.assert:
        that:
          - restic_restore_plan | length == 2
          - restic_restore_plan | map(attribute="app") | sort | list == ["cert-data", "paperless"]

    - name: Read restore execution tasks
      ansible.builtin.slurp:
        src: "{{ playbook_dir }}/../roles/restic_restore/tasks/{{ item }}"
      loop:
        - execute.yml
        - execute_prepare_app.yml
        - execute_restore_app.yml
        - execute_resume_app.yml
      register: restic_restore_execution_task_files

    - name: Assert execution uses production restore guardrails
      ansible.builtin.assert:
        that:
          - "'Remove stale restic restore job' in (restic_restore_execution_task_files.results | map(attribute='content') | map('b64decode') | join('\\n'))"
          - "'kubernetes.core.k8s_json_patch' in (restic_restore_execution_task_files.results | map(attribute='content') | map('b64decode') | join('\\n'))"
          - "'--host' in (restic_restore_execution_task_files.results | map(attribute='content') | map('b64decode') | join('\\n'))"
          - "'restic_restore_snapshot_host' in (restic_restore_execution_task_files.results | map(attribute='content') | map('b64decode') | join('\\n'))"
          - "'--tag' in (restic_restore_execution_task_files.results | map(attribute='content') | map('b64decode') | join('\\n'))"
          - "'restic_restore_snapshot_tag' in (restic_restore_execution_task_files.results | map(attribute='content') | map('b64decode') | join('\\n'))"
          - "'--path' in (restic_restore_execution_task_files.results | map(attribute='content') | map('b64decode') | join('\\n'))"
          - "'restic_restore_snapshot_path' in (restic_restore_execution_task_files.results | map(attribute='content') | map('b64decode') | join('\\n'))"
          - "'Read stale restic restore pods' in (restic_restore_execution_task_files.results | map(attribute='content') | map('b64decode') | join('\\n'))"
          - "'Remove stale restic restore pods' in (restic_restore_execution_task_files.results | map(attribute='content') | map('b64decode') | join('\\n'))"
          - "'Assert ApplicationSet exists' in (restic_restore_execution_task_files.results | map(attribute='content') | map('b64decode') | join('\\n'))"
          - "'Prepare planned apps' in (restic_restore_execution_task_files.results | map(attribute='content') | map('b64decode') | join('\\n'))"
          - "'Restore planned app data' in (restic_restore_execution_task_files.results | map(attribute='content') | map('b64decode') | join('\\n'))"
          - "'Resume planned apps' in (restic_restore_execution_task_files.results | map(attribute='content') | map('b64decode') | join('\\n'))"
          - "'block:' in (restic_restore_execution_task_files.results | map(attribute='content') | map('b64decode') | join('\\n'))"
          - "'rescue:' in (restic_restore_execution_task_files.results | map(attribute='content') | map('b64decode') | join('\\n'))"
          - "'item.replicas' in (restic_restore_execution_task_files.results | map(attribute='content') | map('b64decode') | join('\\n'))"
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```sh
task lint:ansible
```

Expected: fail because `ansible/roles/restic_restore` does not exist.

- [ ] **Step 3: Add the test to the existing lint flow**

No Taskfile change is needed if the file is under `ansible/tests/*.yml`; `task lint:ansible` already syntax-checks and runs every file there.

### Task 2: Implement Plan Builder

**Files:**
- Create: `ansible/roles/restic_restore/defaults/main.yml`
- Create: `ansible/roles/restic_restore/tasks/main.yml`
- Create: `ansible/roles/restic_restore/tasks/plan.yml`
- Modify: `ansible/tests/native-conventions.yml`

- [ ] **Step 1: Add role defaults**

Create `ansible/roles/restic_restore/defaults/main.yml`:

```yaml
---
restic_restore_mode: app
restic_restore_app: ""
restic_restore_snapshot: latest
restic_restore_confirm: false
restic_restore_argocd_namespace: argocd
restic_restore_applicationset_name: apps
restic_restore_namespace: selfhosted
restic_restore_job_name: restic-restore
restic_restore_repo_url: rest:http://restic.selfhosted.svc.cluster.local:8000/
restic_restore_rest_username: restic
restic_restore_credentials_secret: restic-credentials
restic_restore_credentials_key: RESTIC_PASSWORD
restic_restore_image: restic/restic:0.19.0
restic_restore_snapshot_root: /data/appdata
restic_restore_snapshot_host: homelab
restic_restore_snapshot_tag: appdata
restic_restore_snapshot_path: /data/appdata
restic_restore_target_root: /restore
restic_restore_appdata_pvc: restic-appdata
restic_restore_retry_lock: 30m
restic_restore_test_mode: false
restic_restore_excluded_apps:
  - restic
  - root
  - media-backup
  - selfhosted-backup
restic_restore_excluded_pvcs:
  - media/media
  - selfhosted/restic-repo
  - selfhosted/restic-appdata
restic_restore_applications: []
restic_restore_pvcs: []
restic_restore_workloads: []
```

- [ ] **Step 2: Add role entrypoint**

Create `ansible/roles/restic_restore/tasks/main.yml`:

```yaml
---
- name: Build restic restore plan
  ansible.builtin.import_tasks: plan.yml

- name: Stop before execution in test mode
  when: restic_restore_test_mode | bool
  ansible.builtin.meta: end_role

- name: Stop after plan when restore is not confirmed
  when: not (restic_restore_confirm | bool)
  ansible.builtin.debug:
    var: restic_restore_plan

- name: End plan-only restore run
  when: not (restic_restore_confirm | bool)
  ansible.builtin.meta: end_role
```

- [ ] **Step 3: Implement live-state loading and plan construction**

Create `ansible/roles/restic_restore/tasks/plan.yml` with these behaviors:

```yaml
---
- name: Normalize restore mode
  ansible.builtin.assert:
    that:
      - restic_restore_mode in ["app", "all"]
      - restic_restore_mode == "all" or restic_restore_app | length > 0
    fail_msg: "Use restic_restore_mode=app with restic_restore_app, or restic_restore_mode=all."

- name: Set effective snapshot
  ansible.builtin.set_fact:
    restic_restore_effective_snapshot: "{{ restic_restore_snapshot | default('latest', true) }}"

- name: Read Argo CD Applications
  when: not (restic_restore_test_mode | bool)
  kubernetes.core.k8s_info:
    kubeconfig: "{{ kubeconfig_path }}"
    context: "{{ kube_context }}"
    api_version: argoproj.io/v1alpha1
    kind: Application
    namespace: "{{ restic_restore_argocd_namespace }}"
  register: restic_restore_live_applications

- name: Read PVCs
  when: not (restic_restore_test_mode | bool)
  kubernetes.core.k8s_info:
    kubeconfig: "{{ kubeconfig_path }}"
    context: "{{ kube_context }}"
    api_version: v1
    kind: PersistentVolumeClaim
  register: restic_restore_live_pvcs

- name: Read Deployments
  when: not (restic_restore_test_mode | bool)
  kubernetes.core.k8s_info:
    kubeconfig: "{{ kubeconfig_path }}"
    context: "{{ kube_context }}"
    api_version: apps/v1
    kind: Deployment
  register: restic_restore_live_deployments

- name: Read StatefulSets
  when: not (restic_restore_test_mode | bool)
  kubernetes.core.k8s_info:
    kubeconfig: "{{ kubeconfig_path }}"
    context: "{{ kube_context }}"
    api_version: apps/v1
    kind: StatefulSet
  register: restic_restore_live_statefulsets

- name: Normalize source facts
  ansible.builtin.set_fact:
    restic_restore_source_applications: "{{ restic_restore_applications if restic_restore_test_mode | bool else restic_restore_live_applications.resources | default([]) }}"
    restic_restore_source_pvcs: "{{ restic_restore_pvcs if restic_restore_test_mode | bool else restic_restore_live_pvcs.resources | default([]) }}"
    restic_restore_source_workloads: >-
      {{
        restic_restore_workloads
        if restic_restore_test_mode | bool
        else (restic_restore_live_deployments.resources | default([])) + (restic_restore_live_statefulsets.resources | default([]))
      }}

- name: Select restore applications
  ansible.builtin.set_fact:
    restic_restore_selected_applications: >-
      {{
        restic_restore_source_applications
        | selectattr('metadata.name', 'defined')
        | rejectattr('metadata.name', 'in', restic_restore_excluded_apps)
        | list
      }}

- name: Restrict selected applications for single app restore
  when: restic_restore_mode == "app"
  ansible.builtin.set_fact:
    restic_restore_selected_applications: "{{ restic_restore_selected_applications | selectattr('metadata.name', 'equalto', restic_restore_app) | list }}"

- name: Assert requested app exists in Argo CD
  when: restic_restore_mode == "app"
  ansible.builtin.assert:
    that:
      - restic_restore_selected_applications | length == 1
    fail_msg: "Argo CD Application not found or excluded: {{ restic_restore_app }}"

- name: Reset restore plan
  ansible.builtin.set_fact:
    restic_restore_plan: []

- name: Build restore plan entries
  ansible.builtin.include_tasks: plan_app.yml
  loop: "{{ restic_restore_selected_applications | sort(attribute='metadata.name') }}"
  loop_control:
    loop_var: restic_restore_application
    label: "{{ restic_restore_application.metadata.name }}"

- name: Assert single app restore has restorable appdata
  when: restic_restore_mode == "app"
  ansible.builtin.assert:
    that:
      - restic_restore_plan | length == 1
    fail_msg: "No restorable nfs-fast appdata PVC found for app: {{ restic_restore_app }}"
```

- [ ] **Step 4: Add `plan_app.yml` helper**

Create `ansible/roles/restic_restore/tasks/plan_app.yml`:

```yaml
---
- name: Record application destination namespace
  ansible.builtin.set_fact:
    restic_restore_app_namespace: "{{ restic_restore_application.spec.destination.namespace }}"

- name: Reset application PVC resource keys
  ansible.builtin.set_fact:
    restic_restore_app_pvc_resource_keys: []

- name: Collect application PVC resource keys
  ansible.builtin.set_fact:
    restic_restore_app_pvc_resource_keys: "{{ restic_restore_app_pvc_resource_keys + [restic_restore_app_pvc_resource_key] }}"
  vars:
    restic_restore_app_pvc_resource_namespace: "{{ restic_restore_resource.namespace | default(restic_restore_app_namespace, true) }}"
    restic_restore_app_pvc_resource_key: "{{ restic_restore_app_pvc_resource_namespace }}/{{ restic_restore_resource.name }}"
  when: restic_restore_resource.kind == "PersistentVolumeClaim"
  loop: "{{ restic_restore_application.status.resources | default([]) }}"
  loop_control:
    loop_var: restic_restore_resource
    label: "{{ restic_restore_resource.kind }}/{{ restic_restore_resource.name }}"

- name: Select restorable PVCs
  ansible.builtin.set_fact:
    restic_restore_app_pvcs: []

- name: Add restorable appdata PVC
  ansible.builtin.set_fact:
    restic_restore_app_pvcs: "{{ restic_restore_app_pvcs + [restic_restore_pvc] }}"
  vars:
    restic_restore_pvc_key: "{{ restic_restore_pvc.metadata.namespace }}/{{ restic_restore_pvc.metadata.name }}"
  when:
    - restic_restore_pvc_key in restic_restore_app_pvc_resource_keys
    - restic_restore_pvc.spec.storageClassName | default('') == "nfs-fast"
    - restic_restore_pvc_key not in restic_restore_excluded_pvcs
  loop: "{{ restic_restore_source_pvcs }}"
  loop_control:
    loop_var: restic_restore_pvc
    label: "{{ restic_restore_pvc.metadata.namespace }}/{{ restic_restore_pvc.metadata.name }}"

- name: Build PVC key list
  ansible.builtin.set_fact:
    restic_restore_app_pvc_full_names: "{{ restic_restore_app_pvcs | map(attribute='metadata.namespace') | zip(restic_restore_app_pvcs | map(attribute='metadata.name')) | map('join', '/') | list }}"

- name: Build PVC path lists
  ansible.builtin.set_fact:
    restic_restore_app_pvc_paths: "{{ restic_restore_app_pvc_full_names | map('regex_replace', '^', restic_restore_snapshot_root + '/') | list }}"
    restic_restore_app_restore_paths: "{{ restic_restore_app_pvc_full_names | map('regex_replace', '^', restic_restore_target_root + restic_restore_snapshot_root + '/') | list }}"

- name: Reset application scalable workload keys
  ansible.builtin.set_fact:
    restic_restore_app_workload_keys: []

- name: Collect application scalable workload keys
  ansible.builtin.set_fact:
    restic_restore_app_workload_keys: "{{ restic_restore_app_workload_keys + [restic_restore_app_workload_key] }}"
  vars:
    restic_restore_app_workload_namespace: "{{ restic_restore_resource.namespace | default(restic_restore_app_namespace, true) }}"
    restic_restore_app_workload_key: "{{ restic_restore_app_workload_namespace }}/{{ restic_restore_resource.kind }}/{{ restic_restore_resource.name }}"
  when: restic_restore_resource.kind in ["Deployment", "StatefulSet"]
  loop: "{{ restic_restore_application.status.resources | default([]) }}"
  loop_control:
    loop_var: restic_restore_resource
    label: "{{ restic_restore_resource.kind }}/{{ restic_restore_resource.name }}"

- name: Select scalable app workloads
  ansible.builtin.set_fact:
    restic_restore_app_workloads: []

- name: Add scalable workload for this app
  ansible.builtin.set_fact:
    restic_restore_app_workloads: "{{ restic_restore_app_workloads + [restic_restore_workload_ref] }}"
  vars:
    restic_restore_workload_key: "{{ restic_restore_workload.metadata.namespace }}/{{ restic_restore_workload.kind }}/{{ restic_restore_workload.metadata.name }}"
    restic_restore_workload_ref:
      api_version: apps/v1
      kind: "{{ restic_restore_workload.kind }}"
      namespace: "{{ restic_restore_workload.metadata.namespace }}"
      name: "{{ restic_restore_workload.metadata.name }}"
      replicas: "{{ (restic_restore_workload.spec.replicas | default(1)) | int }}"
  when:
    - restic_restore_workload_key in restic_restore_app_workload_keys
  loop: "{{ restic_restore_source_workloads }}"
  loop_control:
    loop_var: restic_restore_workload
    label: "{{ restic_restore_workload.metadata.namespace }}/{{ restic_restore_workload.metadata.name }}"

- name: Add app entry to restore plan
  when: restic_restore_app_pvc_paths | length > 0
  ansible.builtin.set_fact:
    restic_restore_plan: "{{ restic_restore_plan + [restic_restore_app_plan_entry] }}"
  vars:
    restic_restore_app_plan_entry:
      app: "{{ restic_restore_application.metadata.name }}"
      namespace: "{{ restic_restore_app_namespace }}"
      pvc_paths: "{{ restic_restore_app_pvc_paths }}"
      restore_paths: "{{ restic_restore_app_restore_paths }}"
      workloads: "{{ restic_restore_app_workloads | sort(attribute='name') }}"
      had_sync_policy: "{{ restic_restore_application.spec.syncPolicy is defined }}"
      sync_policy: "{{ restic_restore_application.spec.syncPolicy | default({}) }}"
      had_automated_sync: "{{ restic_restore_application.spec.syncPolicy.automated is defined }}"
```

- [ ] **Step 5: Update native convention test scope**

Modify `ansible/tests/native-conventions.yml` so `conventions_role_files` includes:

```yaml
      - ansible/roles/restic_restore/defaults/main.yml
```

Modify the `Find Ansible task files` paths to include:

```yaml
          - "{{ conventions_repo_root }}/ansible/roles/restic_restore/tasks"
```

- [ ] **Step 6: Run the plan tests**

Run:

```sh
task lint:ansible
```

Expected: pass.

### Task 3: Implement Restore Execution

**Files:**
- Create: `ansible/roles/restic_restore/tasks/execute.yml`
- Create: `ansible/roles/restic_restore/tasks/execute_prepare_app.yml`
- Create: `ansible/roles/restic_restore/tasks/execute_restore_app.yml`
- Create: `ansible/roles/restic_restore/tasks/execute_resume_app.yml`
- Modify: `ansible/roles/restic_restore/tasks/main.yml`

- [ ] **Step 1: Add execution handoff**

Modify `ansible/roles/restic_restore/tasks/main.yml` after the plan-only guard:

```yaml
- name: Execute confirmed restic restore
  ansible.builtin.import_tasks: execute.yml
```

- [ ] **Step 2: Add destructive execution tasks**

Create `ansible/roles/restic_restore/tasks/execute.yml`:

```yaml
---
- name: Assert restore plan is not empty
  ansible.builtin.assert:
    that:
      - restic_restore_plan | length > 0
    fail_msg: "No restorable appdata PVCs found."

- name: Remove stale restic restore job
  kubernetes.core.k8s:
    kubeconfig: "{{ kubeconfig_path }}"
    context: "{{ kube_context }}"
    api_version: batch/v1
    kind: Job
    name: "{{ restic_restore_job_name }}"
    namespace: "{{ restic_restore_namespace }}"
    state: absent
    wait: true
    wait_timeout: 120

- name: Read stale restic restore pods
  kubernetes.core.k8s_info:
    kubeconfig: "{{ kubeconfig_path }}"
    context: "{{ kube_context }}"
    api_version: v1
    kind: Pod
    namespace: "{{ restic_restore_namespace }}"
    label_selectors:
      - "job-name={{ restic_restore_job_name }}"
  register: restic_restore_stale_pods

- name: Remove stale restic restore pods
  kubernetes.core.k8s:
    kubeconfig: "{{ kubeconfig_path }}"
    context: "{{ kube_context }}"
    api_version: v1
    kind: Pod
    name: "{{ item.metadata.name }}"
    namespace: "{{ restic_restore_namespace }}"
    state: absent
    wait: true
    wait_timeout: 120
  loop: "{{ restic_restore_stale_pods.resources | default([]) }}"
  loop_control:
    label: "{{ item.metadata.name }}"

- name: Run confirmed restore transaction
  block:
    - name: Create restic restore job
      kubernetes.core.k8s:
        kubeconfig: "{{ kubeconfig_path }}"
        context: "{{ kube_context }}"
        state: present
        definition:
          apiVersion: batch/v1
          kind: Job
          metadata:
            name: "{{ restic_restore_job_name }}"
            namespace: "{{ restic_restore_namespace }}"
          spec:
            template:
              spec:
                restartPolicy: Never
                containers:
                  - name: restic
                    image: "{{ restic_restore_image }}"
                    command:
                      - /bin/sh
                      - -c
                      - sleep 3600
                    env:
                      - name: RESTIC_REPOSITORY
                        value: "{{ restic_restore_repo_url }}"
                      - name: RESTIC_REST_USERNAME
                        value: "{{ restic_restore_rest_username }}"
                      - name: RESTIC_REST_PASSWORD
                        valueFrom:
                          secretKeyRef:
                            name: "{{ restic_restore_credentials_secret }}"
                            key: "{{ restic_restore_credentials_key }}"
                      - name: RESTIC_PASSWORD
                        valueFrom:
                          secretKeyRef:
                            name: "{{ restic_restore_credentials_secret }}"
                            key: "{{ restic_restore_credentials_key }}"
                    volumeMounts:
                      - name: appdata
                        mountPath: "{{ restic_restore_target_root }}{{ restic_restore_snapshot_root }}"
                volumes:
                  - name: appdata
                    persistentVolumeClaim:
                      claimName: "{{ restic_restore_appdata_pvc }}"

    - name: Read current ApplicationSet sync policy
      kubernetes.core.k8s_info:
        kubeconfig: "{{ kubeconfig_path }}"
        context: "{{ kube_context }}"
        api_version: argoproj.io/v1alpha1
        kind: ApplicationSet
        namespace: "{{ restic_restore_argocd_namespace }}"
        name: "{{ restic_restore_applicationset_name }}"
      register: restic_restore_applicationset_info

    - name: Assert ApplicationSet exists
      ansible.builtin.assert:
        that:
          - restic_restore_applicationset_info.resources | length == 1
        fail_msg: "ApplicationSet not found: {{ restic_restore_argocd_namespace }}/{{ restic_restore_applicationset_name }}"

    - name: Record current ApplicationSet sync policy
      ansible.builtin.set_fact:
        restic_restore_applicationset_had_sync_policy: "{{ restic_restore_applicationset_info.resources[0].spec.syncPolicy is defined }}"
        restic_restore_applicationset_original_sync_policy: "{{ restic_restore_applicationset_info.resources[0].spec.syncPolicy | default({}) }}"

    - name: Read restic restore job pod
      kubernetes.core.k8s_info:
        kubeconfig: "{{ kubeconfig_path }}"
        context: "{{ kube_context }}"
        api_version: v1
        kind: Pod
        namespace: "{{ restic_restore_namespace }}"
        label_selectors:
          - "job-name={{ restic_restore_job_name }}"
      register: restic_restore_job_pods
      until:
        - restic_restore_job_pods.resources | length == 1
        - restic_restore_job_pods.resources[0].status.phase == "Running"
        - restic_restore_job_pods.resources[0].status.containerStatuses | default([]) | selectattr('ready', 'equalto', true) | list | length == 1
      retries: 30
      delay: 2

    - name: Record restore pod name
      ansible.builtin.set_fact:
        restic_restore_pod_name: "{{ restic_restore_job_pods.resources[0].metadata.name }}"

    - name: Pause generated app updates
      kubernetes.core.k8s:
        kubeconfig: "{{ kubeconfig_path }}"
        context: "{{ kube_context }}"
        state: patched
        definition:
          apiVersion: argoproj.io/v1alpha1
          kind: ApplicationSet
          metadata:
            name: "{{ restic_restore_applicationset_name }}"
            namespace: "{{ restic_restore_argocd_namespace }}"
          spec:
            syncPolicy:
              applicationsSync: create-only

    - name: Prepare planned apps
      ansible.builtin.include_tasks: execute_prepare_app.yml
      loop: "{{ restic_restore_plan }}"
      loop_control:
        loop_var: restic_restore_app_plan
        label: "{{ restic_restore_app_plan.app }}"

    - name: Restore planned app data
      ansible.builtin.include_tasks: execute_restore_app.yml
      loop: "{{ restic_restore_plan }}"
      loop_control:
        loop_var: restic_restore_app_plan
        label: "{{ restic_restore_app_plan.app }}"

    - name: Resume planned apps
      ansible.builtin.include_tasks: execute_resume_app.yml
      loop: "{{ restic_restore_plan }}"
      loop_control:
        loop_var: restic_restore_app_plan
        label: "{{ restic_restore_app_plan.app }}"

    - name: Restore original ApplicationSet sync policy
      when: restic_restore_applicationset_had_sync_policy | bool
      kubernetes.core.k8s:
        kubeconfig: "{{ kubeconfig_path }}"
        context: "{{ kube_context }}"
        state: patched
        definition:
          apiVersion: argoproj.io/v1alpha1
          kind: ApplicationSet
          metadata:
            name: "{{ restic_restore_applicationset_name }}"
            namespace: "{{ restic_restore_argocd_namespace }}"
          spec:
            syncPolicy: "{{ restic_restore_applicationset_original_sync_policy }}"

    - name: Remove temporary ApplicationSet sync policy
      when: not (restic_restore_applicationset_had_sync_policy | bool)
      kubernetes.core.k8s_json_patch:
        kubeconfig: "{{ kubeconfig_path }}"
        context: "{{ kube_context }}"
        api_version: argoproj.io/v1alpha1
        kind: ApplicationSet
        namespace: "{{ restic_restore_argocd_namespace }}"
        name: "{{ restic_restore_applicationset_name }}"
        patch:
          - op: remove
            path: /spec/syncPolicy

    - name: Delete restic restore job after successful restore
      kubernetes.core.k8s:
        kubeconfig: "{{ kubeconfig_path }}"
        context: "{{ kube_context }}"
        api_version: batch/v1
        kind: Job
        name: "{{ restic_restore_job_name }}"
        namespace: "{{ restic_restore_namespace }}"
        state: absent
        wait: true
        wait_timeout: 120

  rescue:
    - name: Stop after failed destructive restore
      ansible.builtin.fail:
        msg: >-
          Restic restore failed after execution started. The ApplicationSet or
          individual Argo CD app sync policies may still be paused, one or more
          workloads may still be scaled to zero or partially resumed, and the
          restore job is left for inspection. Do not manually resume apps until
          the restored data has been inspected.
```

The rescue path intentionally does not scale apps back up or re-enable app sync.
Before the resume phase, that leaves every planned workload down for operator
inspection instead of starting apps on partial data. During the resume phase,
data restore has completed, but some workloads or sync policies may already be
resumed while others remain paused.

- [ ] **Step 3: Add phased per-app execution helpers**

Create `ansible/roles/restic_restore/tasks/execute_prepare_app.yml`:

```yaml
---
- name: Disable Argo CD automated sync for app
  when: restic_restore_app_plan.had_automated_sync | bool
  kubernetes.core.k8s_json_patch:
    kubeconfig: "{{ kubeconfig_path }}"
    context: "{{ kube_context }}"
    api_version: argoproj.io/v1alpha1
    kind: Application
    namespace: "{{ restic_restore_argocd_namespace }}"
    name: "{{ restic_restore_app_plan.app }}"
    patch:
      - op: remove
        path: /spec/syncPolicy/automated

- name: Scale app workloads down
  kubernetes.core.k8s_scale:
    kubeconfig: "{{ kubeconfig_path }}"
    context: "{{ kube_context }}"
    api_version: "{{ item.api_version }}"
    kind: "{{ item.kind }}"
    namespace: "{{ item.namespace }}"
    name: "{{ item.name }}"
    replicas: 0
    wait: true
    wait_timeout: 300
  loop: "{{ restic_restore_app_plan.workloads }}"
  loop_control:
    label: "{{ item.namespace }}/{{ item.kind }}/{{ item.name }}"

- name: Validate restore delete paths
  ansible.builtin.assert:
    that:
      - item is match('^/restore/data/appdata/.+')
    fail_msg: "Refusing unsafe restore path: {{ item }}"
  loop: "{{ restic_restore_app_plan.restore_paths }}"

- name: Delete current PVC contents
  kubernetes.core.k8s_exec:
    kubeconfig: "{{ kubeconfig_path }}"
    context: "{{ kube_context }}"
    namespace: "{{ restic_restore_namespace }}"
    pod: "{{ restic_restore_pod_name }}"
    command: >-
      sh -ceu "if [ -d '{{ item }}' ]; then find '{{ item }}' -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +; else mkdir -p '{{ item }}'; fi"
  loop: "{{ restic_restore_app_plan.restore_paths }}"
```

Create `ansible/roles/restic_restore/tasks/execute_restore_app.yml`:

```yaml
---
- name: Restore app PVC paths
  kubernetes.core.k8s_exec:
    kubeconfig: "{{ kubeconfig_path }}"
    context: "{{ kube_context }}"
    namespace: "{{ restic_restore_namespace }}"
    pod: "{{ restic_restore_pod_name }}"
    command: >-
      restic --retry-lock {{ restic_restore_retry_lock }} restore {{ restic_restore_effective_snapshot }}
      --host {{ restic_restore_snapshot_host }}
      --tag {{ restic_restore_snapshot_tag }}
      --path {{ restic_restore_snapshot_path }}
      {{ restic_restore_app_plan.pvc_paths | map('regex_replace', '^(.*)$', '--include \\1') | join(' ') }}
      --exclude-xattr '*'
      --target {{ restic_restore_target_root }}
```

Create `ansible/roles/restic_restore/tasks/execute_resume_app.yml`:

```yaml
---
- name: Scale app workloads up
  kubernetes.core.k8s_scale:
    kubeconfig: "{{ kubeconfig_path }}"
    context: "{{ kube_context }}"
    api_version: "{{ item.api_version }}"
    kind: "{{ item.kind }}"
    namespace: "{{ item.namespace }}"
    name: "{{ item.name }}"
    replicas: "{{ item.replicas }}"
    wait: true
    wait_timeout: 300
  loop: "{{ restic_restore_app_plan.workloads }}"
  loop_control:
    label: "{{ item.namespace }}/{{ item.kind }}/{{ item.name }}"

- name: Restore original Argo CD sync policy for app
  when: restic_restore_app_plan.had_sync_policy | bool
  kubernetes.core.k8s:
    kubeconfig: "{{ kubeconfig_path }}"
    context: "{{ kube_context }}"
    state: patched
    definition:
      apiVersion: argoproj.io/v1alpha1
      kind: Application
      metadata:
        name: "{{ restic_restore_app_plan.app }}"
        namespace: "{{ restic_restore_argocd_namespace }}"
      spec:
        syncPolicy: "{{ restic_restore_app_plan.sync_policy }}"
```

- [ ] **Step 4: Run syntax and contract checks**

Run:

```sh
task lint:ansible
```

Expected: pass.

### Task 4: Add Playbook And Taskfile Commands

**Files:**
- Create: `ansible/playbooks/restic-restore.yml`
- Modify: `Taskfile.yaml`
- Modify: `ansible/tests/native-conventions.yml`

- [ ] **Step 1: Add playbook**

Create `ansible/playbooks/restic-restore.yml`:

```yaml
---
- name: Restore Kubernetes appdata from shared restic repo
  hosts: localhost
  gather_facts: false
  roles:
    - role: restic_restore
```

- [ ] **Step 2: Add Taskfile wrappers**

Add tasks near the Argo operations in `Taskfile.yaml`:

```yaml
  restic:restore:
    desc: Plan or run a restic restore for one Argo CD app
    interactive: true
    dir: "{{.TASKFILE_DIR}}"
    deps:
      - task: ansible:check
    vars:
      app: '{{.app | default ""}}'
      snapshot: '{{.snapshot | default "latest"}}'
      confirm_restore: '{{.confirm_restore | default "false"}}'
    requires:
      vars:
        - app
    cmds:
      - '"{{.ANSIBLE_PLAYBOOK}}" ansible/playbooks/restic-restore.yml -e "restic_restore_mode=app" -e "restic_restore_app={{.app}}" -e "restic_restore_snapshot={{.snapshot}}" -e "restic_restore_confirm={{.confirm_restore}}"'

  restic:restore-all:
    desc: Plan or run a restic restore for all appdata PVCs
    interactive: true
    dir: "{{.TASKFILE_DIR}}"
    deps:
      - task: ansible:check
    vars:
      snapshot: '{{.snapshot | default "latest"}}'
      confirm_restore: '{{.confirm_restore | default "false"}}'
    cmds:
      - '"{{.ANSIBLE_PLAYBOOK}}" ansible/playbooks/restic-restore.yml -e "restic_restore_mode=all" -e "restic_restore_snapshot={{.snapshot}}" -e "restic_restore_confirm={{.confirm_restore}}"'
```

- [ ] **Step 3: Assert Taskfile includes restore wrappers**

Add to `ansible/tests/native-conventions.yml` under the Taskfile assertion:

```yaml
          - "'restic:restore:' in (conventions_taskfile.content | b64decode)"
          - "'restic:restore-all:' in (conventions_taskfile.content | b64decode)"
```

- [ ] **Step 4: Run checks**

Run:

```sh
task fmt
task lint:ansible
```

Expected: pass.

### Task 5: Update Documentation

**Files:**
- Modify: `docs/restic-backup-restore-runbook.md`

- [ ] **Step 1: Replace manual restore procedure with Ansible usage**

Update the runbook so the primary commands are:

```sh
task restic:restore app=paperless
task restic:restore app=paperless confirm_restore=true
task restic:restore app=paperless snapshot=<snapshot-id> confirm_restore=true
task restic:restore-all
task restic:restore-all confirm_restore=true
```

Document that `snapshot` defaults to `latest`, plan-only mode is the default, and `confirm_restore=true` is required before deletion or restore.

- [ ] **Step 2: Keep DR ordering notes**

Keep a concise DR section that says:

```text
1. Rebuild Talos/Kubernetes.
2. Restore or reattach /mnt/dpool/restic.
3. Recreate /mnt/spool/appdata.
4. Let Argo CD deploy External Secrets and restic.
5. Run task restic:restore-all first without confirmation.
6. Review the plan.
7. Run task restic:restore-all confirm_restore=true.
8. Verify apps.
9. Run a fresh backup.
```

- [ ] **Step 3: Run full verification**

Run:

```sh
task fmt
task lint
```

Expected: pass.

### Task 6: Commit And Update PR

**Files:**
- All files modified above

- [ ] **Step 1: Inspect final diff**

Run:

```sh
git status --short
git diff --stat
git diff --check
```

Expected: only Ansible restore role/playbook/tests, Taskfile, and restic runbook changes.

- [ ] **Step 2: Commit implementation**

Run:

```sh
git add ansible/playbooks/restic-restore.yml ansible/roles/restic_restore ansible/tests/restic-restore.yml ansible/tests/native-conventions.yml Taskfile.yaml docs/restic-backup-restore-runbook.md
git commit -m "feat(restic): automate appdata restores"
```

- [ ] **Step 3: Push PR branch**

Run:

```sh
git push
```

Expected: existing PR `codex-restic-shared-repo-cleanup` is updated.
