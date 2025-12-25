## ADDED Requirements

### Requirement: Node-RED Deployment

The home-automation stack SHALL include a Node-RED deployment for flow-based automation programming.

#### Scenario: Node-RED runs with persistent storage

- **WHEN** Node-RED is deployed via ArgoCD
- **THEN** the system provisions a 10Gi persistent volume at `/data`
- **AND** Node-RED stores flows, credentials, and settings persistently
- **AND** data survives pod restarts

#### Scenario: Node-RED uses official image

- **WHEN** configuring the Node-RED container
- **THEN** the system uses the official `nodered/node-red:latest` image
- **AND** the image includes Node.js runtime and all dependencies

#### Scenario: Node-RED runs as non-root

- **WHEN** Node-RED pod is created
- **THEN** the pod runs with uid 1000, gid 1000
- **AND** fsGroup is set to 1000 for volume permissions
- **AND** the container drops all capabilities
- **AND** privilege escalation is disabled

### Requirement: Node-RED Web Interface Access

The Node-RED web interface SHALL be accessible via HTTPS through the Istio Gateway.

#### Scenario: Node-RED UI accessible via domain

- **WHEN** accessing `https://nodered.edgard.org` from VPN
- **THEN** the Node-RED editor UI is served
- **AND** TLS is terminated by the Istio Gateway
- **AND** traffic routes to Node-RED service on port 1880

#### Scenario: HTTPRoute configured correctly

- **WHEN** the HTTPRoute resource is created
- **THEN** it references the `gateway` in `platform-system` namespace
- **AND** it uses the `https` section for TLS
- **AND** backend routes to the `main` service identifier on port 1880

### Requirement: Node-RED Health Monitoring

Node-RED SHALL be monitored for health and availability.

#### Scenario: Kubernetes probes configured

- **WHEN** Node-RED container starts
- **THEN** startup probe checks port 1880 for initial readiness
- **AND** liveness probe detects process health
- **AND** readiness probe confirms flows are loaded

#### Scenario: Gatus monitoring enabled

- **WHEN** the Node-RED service is created
- **THEN** it has label `gatus.edgard.org/enabled: "true"`
- **AND** Gatus discovers and monitors the service
- **AND** health checks match Kubernetes probe configuration

### Requirement: MQTT Broker Integration

Node-RED SHALL be configured to integrate with the existing Mosquitto MQTT broker.

#### Scenario: Mosquitto service accessible

- **WHEN** Node-RED needs to connect to MQTT
- **THEN** the Mosquitto broker is reachable at `mqtt://mosquitto.home-automation.svc.cluster.local:1883`
- **AND** the broker allows anonymous connections
- **AND** Node-RED can publish and subscribe to topics

#### Scenario: Environment variable provides broker address

- **WHEN** Node-RED container starts
- **THEN** an environment variable documents the Mosquitto service address
- **AND** users can reference this in MQTT node configuration

### Requirement: Homepage Dashboard Integration

Node-RED SHALL appear in the Homepage dashboard for easy access.

#### Scenario: Homepage annotations configured

- **WHEN** the HTTPRoute is created
- **THEN** it includes annotation `gethomepage.dev/enabled: "true"`
- **AND** it includes annotation `gethomepage.dev/name: Node-RED`
- **AND** it includes annotation `gethomepage.dev/group: Home Automation`
- **AND** it includes annotation `gethomepage.dev/icon: node-red.svg`
- **AND** it includes annotation `gethomepage.dev/app: nodered`

### Requirement: Timezone Configuration

Node-RED SHALL run with correct timezone for automation scheduling.

#### Scenario: Timezone set via environment

- **WHEN** Node-RED container starts
- **THEN** the `TZ` environment variable is set
- **AND** Node-RED uses this timezone for logs and scheduling
- **AND** users can override the timezone in values.yaml

### Requirement: App Template Consistency

Node-RED deployment SHALL follow the project's app-template patterns.

#### Scenario: Uses app-template v4.5.0

- **WHEN** the Node-RED Helm chart is referenced
- **THEN** it uses `oci://ghcr.io/bjw-s-labs/helm/app-template` version 4.5.0
- **AND** configuration follows the standard structure order

#### Scenario: Standard deployment configuration

- **WHEN** the Node-RED controller is configured
- **THEN** it uses type `deployment` with 1 replica
- **AND** strategy is set to `Recreate`
- **AND** controller name is `main` with container name `app`

#### Scenario: No resource limits

- **WHEN** configuring Node-RED resources
- **THEN** limits and requests are set to null
- **AND** this renders as `resources: {}`
- **AND** follows project policy for VPN-protected unlimited resources

### Requirement: ArgoCD Application Discovery

The Node-RED application SHALL be automatically discovered and managed by ArgoCD.

#### Scenario: Application files in correct location

- **WHEN** Node-RED files are created
- **THEN** they exist at `apps/home-automation/nodered/config.yaml`
- **AND** they exist at `apps/home-automation/nodered/values.yaml`
- **AND** the ApplicationSet pattern matches `apps/home-automation/*/config.yaml`

#### Scenario: ArgoCD syncs automatically

- **WHEN** Node-RED files are committed to the repository
- **THEN** ArgoCD ApplicationSet discovers the new application
- **AND** ArgoCD creates an Application resource
- **AND** ArgoCD syncs the Helm chart to the cluster
- **AND** Node-RED deploys in the `home-automation` namespace
