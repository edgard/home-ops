provider "tailscale" {
  oauth_client_id     = data.bitwarden-secrets_secret.tailscale_client_id.value
  oauth_client_secret = data.bitwarden-secrets_secret.tailscale_client_secret.value
  tailnet             = "-" # Uses default tailnet
}

# 1. DNS Configuration (MagicDNS for operator hostnames)
resource "tailscale_dns_preferences" "config" {
  magic_dns = true
}

# 2. ACL & Auto-Approval (Gateway-only exposure)
resource "tailscale_acl" "policy" {
  acl = jsonencode({
    # Define tags
    "tagOwners" : {
      "tag:k8s-operator" : ["autogroup:admin"],
      "tag:k8s-gateway" : ["tag:k8s-operator"],
    },
    # Allow access to gateway ports
    "acls" : [
      { "action" : "accept", "src" : ["*"], "dst" : ["tag:k8s-gateway:443"] },
      { "action" : "accept", "src" : ["*"], "dst" : ["tag:k8s-gateway:80"] },
    ],
    # Auto-approve gateway service exposure
    "autoApprovers" : {
      "services" : {
        "tag:k8s-gateway" : ["tag:k8s-operator"],
      },
    },
  })
}
