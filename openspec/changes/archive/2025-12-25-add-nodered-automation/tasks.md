# Implementation Tasks

## 1. Create Node-RED Application Structure

- [x] 1.1 Create `apps/home-automation/nodered/` directory
- [x] 1.2 Create `config.yaml` with app-template chart reference (v4.5.0)
- [x] 1.3 Create `values.yaml` with Node-RED configuration

## 2. Configure Node-RED Deployment

- [x] 2.1 Configure controller using official `nodered/node-red:latest` image
- [x] 2.2 Set deployment strategy to `Recreate` (single-node cluster pattern)
- [x] 2.3 Configure security context (non-root: uid/gid 1000)
- [x] 2.4 Set timezone via `TZ` environment variable
- [x] 2.5 Configure startup, liveness, and readiness probes on port 1880
- [x] 2.6 Set resource limits to null (unlimited, per project policy)

## 3. Configure Persistence

- [x] 3.1 Create PVC for `/data` directory (10Gi, local-fast storage class)
- [x] 3.2 Ensure proper ownership (uid 1000 for Node-RED user)

## 4. Configure Networking

- [x] 4.1 Create ClusterIP service on port 1880
- [x] 4.2 Add Gatus monitoring label (`gatus.edgard.org/enabled: "true"`)
- [x] 4.3 Create HTTPRoute with hostname `nodered.edgard.org`
- [x] 4.4 Add Homepage dashboard annotations (name, group, icon)
- [x] 4.5 Configure route to use Istio Gateway (platform-system/gateway, HTTPS section)

## 5. Validation

- [x] 5.1 Run `task lint` to validate YAML formatting
- [ ] 5.2 Verify ArgoCD discovers the new application
- [ ] 5.3 Test Node-RED UI accessibility via VPN at https://nodered.edgard.org
- [ ] 5.4 Verify persistent storage is mounted correctly
- [ ] 5.5 Test MQTT connection to Mosquitto broker
- [ ] 5.6 Confirm Gatus health check monitoring is active
- [ ] 5.7 Verify Homepage dashboard entry appears
