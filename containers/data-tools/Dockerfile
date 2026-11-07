FROM docker.io/library/postgres:18.6-trixie@sha256:e3d24f6906d0760bf4da0dae872415391ededefad23fd471c47dc53b0ddf3c42 AS postgres
FROM restic/restic:0.19.1@sha256:136600b6ff6843d61d355f7f71f460a166429f35de6fd11b568fece3c9a4d510 AS restic
FROM docker.io/library/python:3.15.2-slim-trixie@sha256:e97b88e416c3c01eb427b21fd8cd3ebf006e6ee38afcfcc3cae1c54ee2ab0a75
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates rsync redis-tools libgssapi-krb5-2 libldap2 liblz4-1 libzstd1 libkrb5-3 libssl3t64 libreadline8t64 libicu76 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=postgres /usr/lib/postgresql/18 /usr/lib/postgresql/18
COPY --from=postgres /usr/lib/*-linux-gnu/libpq.so.5.* /usr/local/lib/
RUN ldconfig
COPY --from=restic /usr/bin/restic /usr/local/bin/restic
ENV PATH="/usr/lib/postgresql/18/bin:${PATH}" \
    ANSIBLE_CONFIG=/opt/home-ops/containers/data-tools/ansible.cfg \
    ANSIBLE_ROLES_PATH=/opt/home-ops/ansible/roles \
    ANSIBLE_COLLECTIONS_PATH=/opt/ansible/collections \
    PYTHONDONTWRITEBYTECODE=1
COPY containers/data-tools/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY ansible/requirements.yml /tmp/collections.yml
RUN ansible-galaxy collection install -r /tmp/collections.yml -p /opt/ansible/collections
WORKDIR /opt/home-ops
COPY containers/data-tools/ansible.cfg containers/data-tools/ansible.cfg
COPY containers/data-tools/hosts.yml containers/data-tools/hosts.yml
COPY ansible/roles/shared_data ansible/roles/shared_data
COPY ansible/playbooks/shared-data.yml ansible/playbooks/shared-data.yml
ENTRYPOINT ["ansible-playbook", "ansible/playbooks/shared-data.yml"]
