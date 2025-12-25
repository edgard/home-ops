# Change: Add Node-RED to Home Automation Stack

## Why

The user is migrating automation workflows from Home Assistant to Node-RED, requiring a new Node-RED deployment in the home-automation namespace. Node-RED provides a browser-based flow programming tool for event-driven applications, offering greater flexibility for automation logic compared to Home Assistant's built-in automation engine.

## What Changes

- Add new `nodered` application under `apps/home-automation/`
- Deploy Node-RED using the official `nodered/node-red` Docker image
- Follow existing app-template patterns (v4.5.0) consistent with other home-automation apps
- Configure persistent storage for Node-RED flows, credentials, and settings
- Expose Node-RED UI via Istio Gateway with HTTPRoute
- Enable health monitoring via Gatus
- Configure MQTT integration to connect with existing Mosquitto broker
- Set appropriate timezone via environment variable

## Impact

- **Affected specs**: `home-automation-apps` (new capability)
- **Affected code**:
  - New files: `apps/home-automation/nodered/config.yaml`, `apps/home-automation/nodered/values.yaml`
  - ArgoCD will automatically discover and sync the new application via the ApplicationSet
- **Dependencies**: Requires Mosquitto MQTT broker (already deployed)
- **Access**: VPN-only via Tailscale, HTTPS ingress at `nodered.edgard.org`
