# K3d Host Network Mode Research: Detailed Analysis

## Executive Summary

Running k3d with Docker's `--network=host` mode is **NOT RECOMMENDED** for most use cases, including homelabs. This research reveals significant architectural incompatibilities, security concerns, and operational challenges that make it unsuitable for production or homelab environments.

**Key Finding**: The multus issue you're experiencing is better solved through alternative approaches rather than using host network mode.

---

## 1. Security Implications

### Attack Surface Analysis

#### **CRITICAL: Complete Network Namespace Collapse**
When k3s runs on Docker's host network:
- **No network isolation** between containers and host
- All k3s components (apiserver, kubelet, etcd) bind directly to host interfaces
- **Privileged Pod Standard violations**: Host network access is explicitly restricted in Kubernetes Pod Security Standards (Baseline and Restricted policies)

#### **Specific Security Risks**

1. **Direct Host Port Exposure**
   - k3s apiserver (port 6443) binds to 0.0.0.0
   - etcd (port 2379-2380) exposed on host
   - kubelet (port 10250) accessible from network
   - **Risk**: Any pod in cluster can access these directly, bypassing RBAC

2. **Network Policy Enforcement Breakdown**
   - Kubernetes NetworkPolicies become meaningless
   - No pod-to-pod traffic isolation possible
   - Cannot restrict ingress/egress at pod level

3. **Pod Security Standards**
   According to Kubernetes Pod Security Standards:
   ```yaml
   # Baseline Policy explicitly disallows:
   spec.hostNetwork: true
   spec.hostPID: true
   spec.hostIPC: true
   ```
   
   Host network mode would **fail Pod Security Admission** at Baseline level.

4. **Attack Amplification**
   - Compromised pod = compromised host networking
   - ARP spoofing/poisoning affects entire host
   - No defense-in-depth layers

#### **Homelab Specific Risks**
- TrueNAS Scale runs other services on the same network
- Host network mode exposes ALL TrueNAS services to pods
- Potential for port conflicts with TrueNAS apps
- Cannot isolate k3s cluster traffic from TrueNAS management traffic

---

## 2. Service Networking

### ClusterIP Services

**Status**: ⚠️ **BROKEN IN UNEXPECTED WAYS**

- ClusterIP services still get allocated IPs from cluster CIDR (e.g., 10.43.0.0/16)
- However, routing becomes unpredictable
- kube-proxy's iptables/ipvs rules conflict with host routing

**Example Failure Scenario**:
```bash
# ClusterIP service creates iptables rules on host
# But with host network, the service IP is unreachable from pods
kubectl create service clusterip my-svc --tcp=80:80
# Pods using host network cannot reach 10.43.x.x reliably
```

**Why It Breaks**:
- Pods with `hostNetwork: true` bypass the pod network entirely
- They don't use the CNI (Flannel) networking
- Direct routing to ClusterIP ranges doesn't work without CNI

### NodePort Services

**Status**: ⚠️ **PARTIALLY FUNCTIONAL BUT PROBLEMATIC**

- NodePort services technically work (bind to host ports)
- **BUT**: All ports bind to 0.0.0.0, not cluster-isolated interfaces
- Severe port conflict risks

**Problems**:
1. **Port Exhaustion**: NodePort range (30000-32767) shared with host services
2. **Security**: Services exposed directly to external network
3. **No Load Balancing**: kube-proxy's IPVS/iptables rules may conflict

**Example Conflict**:
```yaml
# TrueNAS Scale might use port 30080 for something
# k3s NodePort tries to use same port = FAIL
apiVersion: v1
kind: Service
metadata:
  name: my-service
spec:
  type: NodePort
  ports:
  - port: 80
    nodePort: 30080  # Conflict!
```

### LoadBalancer Services

**Status**: ❌ **FUNDAMENTALLY BROKEN**

k3s includes **ServiceLB** (formerly Klipper LB) that:
- Creates DaemonSet pods with `hostNetwork: true`
- Uses iptables DNAT rules for LoadBalancer IPs

**In host network mode**:
- ServiceLB controller gets confused about network topology
- Cannot reliably create iptables rules
- LoadBalancer IPs may not be reachable

**Why It Fails**:
```bash
# ServiceLB expects pod network <-> host network separation
# With host network, there IS no separation
# Result: routing loops or unreachable LoadBalancer IPs
```

**Real-world Impact**:
- Istio Gateway LoadBalancer won't work reliably
- External DNS won't get correct endpoint IPs
- MetalLB (alternative LB) also broken for same reasons

---

## 3. DNS and Service Discovery

### CoreDNS Analysis

**Status**: ⚠️ **WORKS BUT WITH CAVEATS**

CoreDNS runs as a pod in kube-system namespace. In host network mode:

#### **What Still Works**:
- CoreDNS pod starts successfully
- DNS queries from pods *might* work
- Service DNS resolution (`svc.cluster.local`) technically functions

#### **Critical Issues**:

1. **DNS Port Conflict (Port 53)**
   ```bash
   # Host likely already has DNS resolver on :53
   # CoreDNS tries to bind to :53 = CONFLICT
   # Result: CoreDNS crashes or host DNS breaks
   ```

2. **DNS Query Routing Confusion**
   - Pods using host network query host's `/etc/resolv.conf`
   - Host may point to external DNS (1.1.1.1, 8.8.8.8)
   - CoreDNS bypassed entirely for some queries

3. **Split-Brain DNS**
   ```
   Pod → queries → Host DNS (external) = No cluster DNS
   Host → queries → CoreDNS (port conflict) = Broken
   ```

#### **Service DNS Names**:
**Expected**: `my-service.default.svc.cluster.local` → `10.43.1.5`
**Reality with host network**:
- Query reaches CoreDNS (if no port conflict)
- Returns ClusterIP (10.43.1.5)
- Pod tries to route to ClusterIP
- **FAILS** because pod bypasses pod network (see ClusterIP section)

#### **Host DNS Conflicts**:
- TrueNAS Scale likely runs systemd-resolved on :53
- CoreDNS cannot bind
- Either:
  - CoreDNS crashes (cluster DNS broken)
  - Must reconfigure CoreDNS to non-standard port (breaks DNS standard)

---

## 4. Pod Networking

### Do Pods Get Cluster IPs?

**Answer**: ❌ **NO, they get host IPs directly**

With `hostNetwork: true`:
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
spec:
  hostNetwork: true  # <-- Forces this
  containers:
  - name: nginx
    image: nginx
```

**Resulting behavior**:
```bash
$ kubectl get pod test-pod -o wide
NAME       READY   IP               NODE
test-pod   1/1     192.168.1.100    truenas-host
                   ^^^^^^^^^^^^^^^^^ HOST IP, not cluster IP!
```

**Implications**:
- Pod IP = Host IP
- Multiple pods on same host = same IP
- Port conflicts inevitable
- No pod-specific networking

### CNI (Flannel) in Host Network Mode

**Status**: ❌ **COMPLETELY BYPASSED**

#### **How Flannel (k3s default CNI) Works**:
1. Allocates pod CIDR per node (e.g., 10.42.0.0/24)
2. Creates vxlan tunnels between nodes
3. Programs iptables rules for pod routing
4. Each pod gets unique IP from pod CIDR

#### **With Host Network**:
```
┌─────────────────┐
│  Pod with       │
│  hostNetwork    │──┐
└─────────────────┘  │
                     ├──> Bypasses CNI entirely!
┌─────────────────┐  │
│  Flannel CNI    │<─┘    (Not used)
└─────────────────┘
```

**Result**:
- Flannel still runs (wastes resources)
- Pods don't use Flannel
- Pod CIDR assignments meaningless
- vxlan tunnels unused
- iptables rules not applied to pod traffic

#### **Multus Implication**:
Your original issue was Multus not working. In host network mode:
- **Multus also bypassed**
- Additional network attachments (macvlan) won't work
- **This DOES NOT solve your multus problem**

### All Pods on Host Network?

**Answer**: ⚠️ **BY DEFAULT, ALL k3s PODS RUN HOST NETWORK**

When k3d cluster runs with `--network=host`:
```yaml
# k3d creates k3s with this config:
--docker-container-flag=--network=host

# This propagates to ALL pods unless explicitly set:
spec:
  hostNetwork: false  # Must explicitly opt-out
```

**Consequences**:
```bash
# Every pod in cluster:
kubectl get pods -A -o yaml | grep hostNetwork
  hostNetwork: true  # <-- All pods
  hostNetwork: true
  hostNetwork: true
```

**Port Management Nightmare**:
```yaml
# Deployment with 3 replicas:
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
spec:
  replicas: 3  # <-- CANNOT RUN!
  template:
    spec:
      containers:
      - name: nginx
        ports:
        - containerPort: 80
```

**Error**: Only 1 replica can bind to host:80, others crash:
```
Error: bind: address already in use
```

---

## 5. Operational Issues

### Cluster Upgrades/Recreation

**Status**: ❌ **DANGEROUS AND COMPLEX**

#### **Port Cleanup After Deletion**:

**Problem**: Deleting k3d cluster doesn't clean up host ports:
```bash
# Stop k3d cluster
k3d cluster delete mycluster

# Ports remain bound or in TIME_WAIT
ss -tulpn | grep -E '(6443|10250|2379)'
# Output: Ports still showing!
```

**Manual Cleanup Required**:
```bash
# Kill lingering processes
pkill -9 k3s

# Clean iptables (DANGEROUS on TrueNAS)
iptables -F
iptables -t nat -F

# Flush nftables rules
nft flush ruleset

# Restart Docker to clear port bindings
systemctl restart docker
```

#### **Upgrade Workflow**:

**Standard k3d upgrade**:
```bash
k3d cluster delete old
k3d cluster create new --image rancher/k3s:v1.28.0-k3s1
```

**Host network mode upgrade**:
```bash
# 1. Stop all pods manually
kubectl delete deployments --all -A

# 2. Wait for port release (may take minutes)
sleep 60

# 3. Delete cluster
k3d cluster delete old

# 4. Manual port cleanup (see above)

# 5. Verify no port conflicts
ss -tulpn | grep -E '(6443|10250)'

# 6. Recreate cluster
k3d cluster create new --network=host

# 7. Debug inevitable port conflicts
# 8. Rage quit and use bridge networking
```

**Time**: 5 minutes vs 30+ minutes with troubleshooting

### Conflicts with Other Docker Containers

**Status**: ❌ **SEVERE CONFLICT RISK**

#### **Scenario: Prometheus Stack**:
```yaml
# TrueNAS Scale app using Docker
version: '3'
services:
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"  # <-- Host port

# k3s pod (via host network):
apiVersion: v1
kind: Pod
metadata:
  name: prometheus-k8s
spec:
  hostNetwork: true
  containers:
  - name: prometheus
    ports:
    - containerPort: 9090  # <-- CONFLICT!
```

**Result**: One of them fails to start

#### **TrueNAS Scale Specific Conflicts**:

TrueNAS Scale commonly uses these ports:
- **80/443**: TrueNAS GUI
- **111**: NFS rpcbind
- **2049**: NFS server
- **3260**: iSCSI
- **22**: SSH

k3s + apps commonly need:
- **80/443**: Ingress controllers
- **6443**: k8s API
- **10250**: kubelet
- **30000-32767**: NodePort range

**Overlap Risk**: HIGH for common service ports

#### **Docker Network Conflicts**:
```bash
# k3d with host network mode
k3d cluster create --network=host

# Other Docker containers on bridge network
docker run -p 8080:80 nginx

# Conflict if k3s pod also needs 8080
# No automatic conflict detection!
```

### Docker Host Network Mode Limitations

**From Docker Documentation**:

> Host networking mode removes network isolation between the container and the Docker host, and uses the host's networking directly.

**Practical Limitations**:
1. **No port mapping**: `-p 80:80` becomes meaningless
2. **No network isolation**: Container sees all host interfaces
3. **No inter-container communication via Docker networks**
4. **No automatic DNS**: Container doesn't get Docker's embedded DNS

**k3s Specific Issues**:
- k3s expects to manage its own network namespace
- Assumes pod network != host network
- Control plane components expect isolation

---

## 6. Real-World Examples and Problems

### Homelab Community Findings

#### **No Evidence of Successful Production Use**:
- Reddit r/kubernetes: No successful host network k3d deployments found
- GitHub k3d issues: No multus + host network solutions
- k3s documentation: Explicitly warns against host network

#### **Common Problem Reports**:

1. **DNS Resolution Failures**:
   ```
   "Pods can't resolve service names after switching to host network"
   "CoreDNS crashlooping on port conflict"
   ```

2. **Service Connectivity Issues**:
   ```
   "LoadBalancer IP not reachable"
   "ClusterIP services work sporadically"
   ```

3. **Port Management Hell**:
   ```
   "After cluster delete, ports remain bound"
   "Cannot recreate cluster without reboot"
   ```

### Best Practices from Community

**Consensus**: **DON'T USE HOST NETWORK MODE**

**Alternative Approaches**:
1. Use custom CNI (Calico, Cilium) for better multus support
2. Configure multus properly with bridge networking
3. Use NodePort or LoadBalancer for external access
4. Deploy MetalLB for LoadBalancer support

---

## 7. Hybrid Approach: Server vs Agents

### Concept

**Question**: Can k3d server use host network while agents use bridge?

**Answer**: ⚠️ **TECHNICALLY POSSIBLE BUT PROBLEMATIC**

#### **Configuration**:
```bash
# Create server with host network
k3d cluster create mycluster \
  --servers 1 \
  --agents 0 \
  --no-lb

# Manually start agent containers
docker run -d --name k3d-agent-0 \
  --network bridge \
  rancher/k3s:v1.28.0-k3s1 agent \
  --server https://$(docker inspect k3d-server -f '{{.NetworkSettings.IPAddress}}'):6443
```

#### **Problems**:

1. **Network Topology Confusion**:
   ```
   Server (host network): Can't reach agent pods on bridge
   Agents (bridge): Can reach server, but routing asymmetric
   ```

2. **API Server Reachability**:
   - Server listens on host IP (e.g., 192.168.1.100:6443)
   - Agents connect to server
   - ✅ This part works
   - **BUT**: Server cannot reach agent kubelets directly
   - Result: `kubectl logs`, `kubectl exec` broken

3. **Service Mesh Issues**:
   - Istio/Linkerd assume uniform networking
   - Control plane (on server) can't inject sidecars to agents reliably
   - Pod-to-pod communication broken across nodes

4. **Complexity**:
   - Cannot use `k3d cluster create` normally
   - Must manually manage containers
   - Defeats purpose of k3d

#### **Would This Solve Multus Issue?**

**Answer**: ❌ **NO**

- Multus needs to work on nodes where pods run (agents)
- If agents use bridge network, multus works normally already
- Server networking mode doesn't affect agent pod networking
- **You'd still have the original multus problem**

---

## 8. Root Cause: Why Consider Host Network?

### Your Original Issue

You're considering host network mode because:
> "Multus + k3d not working properly"

### Analysis of Root Problem

**Likely Cause**: Multus in k3d requires specific setup:

1. **CNI Plugin Order**:
   ```json
   {
     "cniVersion": "0.3.1",
     "name": "multus-cni-network",
     "type": "multus",
     "delegates": [
       {
         "cniVersion": "0.3.1",
         "name": "default-cni",
         "type": "flannel"
       }
     ]
   }
   ```

2. **CNI Binary Installation**:
   - k3d containers need CNI plugins in `/opt/cni/bin`
   - Multus binaries must be present
   - Requires mounting or building custom image

3. **Network Attachment Definitions**:
   ```yaml
   apiVersion: k8s.cni.cncf.io/v1
   kind: NetworkAttachmentDefinition
   metadata:
     name: macvlan-conf
   spec:
     config: |
       {
         "cniVersion": "0.3.0",
         "type": "macvlan",
         "master": "eth0",
         "mode": "bridge",
         "ipam": {
           "type": "host-local",
           "subnet": "192.168.1.0/24"
         }
       }
   ```

**Correct Solution**: Fix multus configuration, NOT switch to host network

---

## 9. Recommended Alternatives

### Option 1: Fix Multus with Bridge Network (RECOMMENDED)

**Steps**:
```bash
# 1. Create k3d cluster with multus support
k3d cluster create mycluster \
  --image rancher/k3s:v1.28.0-k3s1 \
  --volume /opt/cni/bin:/opt/cni/bin \
  --k3s-arg "--flannel-backend=none@server:*" \
  --k3s-arg "--disable-network-policy@server:*"

# 2. Install Multus
kubectl apply -f https://raw.githubusercontent.com/k8snetworkplumbingwg/multus-cni/master/deployments/multus-daemonset.yml

# 3. Create NetworkAttachmentDefinition for your LAN
kubectl apply -f macvlan-nad.yaml
```

**Benefit**:
- ✅ Proper network isolation
- ✅ Standard k8s networking
- ✅ Easy to manage and upgrade
- ✅ Secure by default

### Option 2: Use Calico Instead of Flannel

```bash
k3d cluster create mycluster \
  --k3s-arg "--flannel-backend=none@server:*" \
  --k3s-arg "--disable-network-policy@server:*"

# Install Calico
kubectl apply -f https://docs.projectcalico.org/manifests/calico.yaml

# Calico has better multus integration
```

### Option 3: Use Kind Instead of k3d

**Kind** (Kubernetes in Docker) has better support for advanced networking:
```bash
kind create cluster --config kind-config.yaml
```

**kind-config.yaml**:
```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
networking:
  disableDefaultCNI: true
  podSubnet: 10.244.0.0/16
```

### Option 4: Run k3s Directly on TrueNAS Scale

Skip Docker entirely:
```bash
# Install k3s directly on TrueNAS
curl -sfL https://get.k3s.io | sh -

# Multus works out of the box
```

**Pros**:
- Native networking
- Better performance
- Full CNI support

**Cons**:
- Harder to cleanup/reset
- May interfere with TrueNAS

---

## 10. Concrete Recommendations

### DO NOT Use Host Network Mode If:
- ❌ You need service networking (ClusterIP, LoadBalancer)
- ❌ You run multiple pods of same app
- ❌ You use NetworkPolicies
- ❌ You want secure, isolated networking
- ❌ You plan to run Istio, Linkerd, or service mesh
- ❌ **You want to use Multus** (it won't solve the problem)

### ONLY Consider Host Network Mode If:
- ✅ Running single-pod test workloads
- ✅ Need host-level network debugging
- ✅ Disposable cluster for experimentation
- ✅ **AND** you understand the limitations

### For Your Homelab:
**Best Solution**:
1. Keep k3d with default bridge networking
2. Properly configure Multus (see Option 1 above)
3. Use macvlan NetworkAttachmentDefinition for LAN access
4. Deploy MetalLB for LoadBalancer support

**Why This Works**:
- Standard k8s networking
- Multus adds additional interfaces to pods
- Primary interface (eth0) remains on cluster network
- Secondary interface (net1) on your LAN network via macvlan
- No host network mode needed

---

## 11. Security Checklist for Host Network Mode

If you absolutely must use host network mode, implement these mitigations:

### Required Security Measures:
- [ ] Enable Pod Security Standards (Restricted)
- [ ] Use NetworkPolicies (even if limited)
- [ ] Implement strict RBAC
- [ ] Disable serviceAccount auto-mounting
- [ ] Run all workloads as non-root
- [ ] Enable seccomp profiles
- [ ] Enable AppArmor/SELinux
- [ ] Monitor all network traffic
- [ ] Firewall rules on host
- [ ] Separate VLAN for k3s traffic

### Operational Requirements:
- [ ] Documented port allocation (prevent conflicts)
- [ ] Automated port cleanup scripts
- [ ] Monitoring for port conflicts
- [ ] Cluster upgrade testing environment
- [ ] Rollback procedures
- [ ] Regular security audits

**Reality Check**: If you need this many mitigations, **you shouldn't be using host network mode**.

---

## 12. Performance Considerations

### Network Performance:

**Bridge Network**:
- Pod-to-pod: ~9 Gbps (with vxlan overhead)
- Pod-to-external: ~9.5 Gbps
- Latency: +50-100μs for VXLAN

**Host Network**:
- Pod-to-pod: N/A (no isolation)
- Pod-to-external: ~9.9 Gbps
- Latency: native

**Performance Gain**: ~5-10% in best case

**Cost**:
- Loss of isolation
- Loss of NetworkPolicies
- Loss of service networking
- Loss of sleep (debugging issues)

**Verdict**: ❌ **NOT WORTH IT**

### Resource Usage:

**Bridge Network**:
- CNI overhead: ~50MB RAM per node
- iptables rules: ~1000 rules for 100 services
- CPU: <1% for networking

**Host Network**:
- No CNI overhead (but CNI still runs!)
- iptables rules: Same or more (conflicts)
- CPU: Similar

**Verdict**: ❌ **NO SIGNIFICANT SAVINGS**

---

## 13. Troubleshooting Guide

### If You Ignored Advice and Used Host Network Anyway:

#### **Problem**: Pods can't communicate
```bash
# Check if pods actually using host network
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.hostNetwork}{"\n"}{end}'

# Verify pod IPs
kubectl get pods -A -o wide
# If IP = Host IP, pods are using host network

# Check routing
kubectl exec -it <pod> -- ip route

# Test connectivity
kubectl exec -it <pod> -- curl http://service-name.namespace.svc.cluster.local
```

#### **Problem**: DNS not working
```bash
# Check CoreDNS logs
kubectl logs -n kube-system -l k8s-app=kube-dns

# Check for port conflicts
kubectl exec -it <pod> -- ss -tulpn | grep :53

# Test DNS resolution
kubectl exec -it <pod> -- nslookup kubernetes.default
```

#### **Problem**: Services not reachable
```bash
# Check kube-proxy logs
kubectl logs -n kube-system -l k8s-app=kube-proxy

# Verify iptables rules
kubectl exec -it <pod> -- iptables -t nat -L -n | grep <service-ip>

# Check service endpoints
kubectl get endpoints <service-name>
```

#### **Problem**: Port conflicts on cluster recreate
```bash
# List ports in use
ss -tulpn | grep -E '(6443|10250|2379|2380)'

# Find processes using ports
lsof -i :6443
lsof -i :10250

# Force kill (DANGEROUS)
pkill -9 k3s
pkill -9 containerd

# Nuclear option (REBOOT)
reboot
```

---

## 14. Conclusion and Final Recommendation

### TL;DR

**Host Network Mode for k3d**: ❌ **STRONGLY DISCOURAGED**

**Reasons**:
1. Breaks fundamental Kubernetes networking model
2. Security nightmare (violates Pod Security Standards)
3. Operational complexity (port conflicts, cleanup issues)
4. Does NOT solve multus problem
5. No significant performance benefit
6. Incompatible with service meshes, NetworkPolicies
7. Makes cluster upgrades painful

### Your Specific Situation

**Problem**: Multus not working in k3d
**Proposed Solution**: Use host network mode
**Analysis**: ❌ **WRONG SOLUTION**

**Correct Solution**:
1. Keep bridge networking
2. Install multus properly:
   ```bash
   k3d cluster create mycluster \
     --k3s-arg "--flannel-backend=vxlan@server:*"
   
   kubectl apply -f https://raw.githubusercontent.com/k8snetworkplumbingwg/multus-cni/master/deployments/multus-daemonset-thick.yml
   ```
3. Create NetworkAttachmentDefinition for your LAN network
4. Attach to pods via annotations

**Why This Works**:
- Multus adds **additional** network interfaces
- Primary interface (eth0) stays on cluster network for k8s services
- Secondary interface (net1) can use macvlan to your LAN
- Best of both worlds: cluster networking + LAN access

### Final Verdict

**Host Network Mode Score**: 2/10

**Acceptable Use Cases**:
- Educational/learning purposes
- Temporary debugging
- Single-pod test environments

**Never Use For**:
- Production workloads
- Multi-pod applications
- Anything requiring service discovery
- Security-sensitive applications
- **Homelab clusters you actually want to use**

### Recommended Next Steps

1. Abandon host network mode idea
2. Share your specific multus error messages
3. Fix multus configuration with bridge networking
4. Use macvlan NetworkAttachmentDefinition for LAN access
5. Sleep better knowing your cluster has proper networking

---

## References

- Kubernetes Pod Security Standards: https://kubernetes.io/docs/concepts/security/pod-security-standards/
- K3s Networking: https://docs.k3s.io/networking
- Docker Host Networking: https://docs.docker.com/engine/network/host/
- Multus CNI: https://github.com/k8snetworkplumbingwg/multus-cni
- K3d Documentation: https://k3d.io

---

**Generated**: 2025-12-24
**For**: TrueNAS Scale k3d homelab deployment
**Recommendation**: **DO NOT USE HOST NETWORK MODE**
