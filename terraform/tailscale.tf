provider "tailscale" {
  oauth_client_id     = data.bitwarden-secrets_secret.tailscale_client_id.value
  oauth_client_secret = data.bitwarden-secrets_secret.tailscale_client_secret.value
  tailnet             = "-" # Uses default tailnet
}

# 1. DNS Configuration (MagicDNS + forward edgard.org to Unifi)
resource "tailscale_dns_preferences" "config" {
  magic_dns = true
}

# 2. Split DNS - forward edgard.org to Unifi DNS
resource "tailscale_dns_split_nameservers" "edgard_org" {
  domain      = "edgard.org"
  nameservers = ["192.168.1.1"]
}

# 3. ACL & Auto-Approval (Subnet router for gateway only)
resource "tailscale_acl" "policy" {
  acl = jsonencode({
    # Define tags
    "tagOwners" : {
      "tag:k8s-router" : ["autogroup:admin"],
    },
    # Allow access to gateway via subnet router
    "acls" : [
      { "action" : "accept", "src" : ["*"], "dst" : ["192.168.1.241:80", "192.168.1.241:443"] },
      { "action" : "accept", "src" : ["*"], "dst" : ["192.168.1.1:53"] },
    ],
    # Auto-approve subnet router routes
    "autoApprovers" : {
      "routes" : {
        "192.168.1.241/32" : ["tag:k8s-router"],
        "192.168.1.1/32" : ["tag:k8s-router"],
      },
    },
  })
}
