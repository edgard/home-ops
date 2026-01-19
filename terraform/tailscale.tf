provider "tailscale" {
  # Redis from TAILSCALE_OAUTH_CLIENT_ID and TAILSCALE_OAUTH_CLIENT_SECRET env vars
  tailnet = "-" # Uses default tailnet
}

# 1. Split DNS Configuration (Minimal: Only specific domains)
resource "tailscale_dns_preferences" "config" {
  magic_dns = false
}

resource "tailscale_dns_split_nameservers" "lan_dns" {
  domain      = "edgard.org"
  nameservers = ["192.168.1.1"]
}

resource "tailscale_dns_split_nameservers" "home_arpa" {
  domain      = "home.arpa"
  nameservers = ["192.168.1.1"]
}

# 2. ACL & Auto-Approval (Minimal: Only allow access to the subnet)
resource "tailscale_acl" "policy" {
  acl = jsonencode({
    # Define tags
    "tagOwners" : {
      "tag:cluster-subnet-router" : ["autogroup:admin"],
    },
    # Minimal Access: Only allow access to the 192.168.1.0/24 subnet
    "acls" : [
      # Allow all devices to reach the LAN subnet
      { "action" : "accept", "src" : ["*"], "dst" : ["192.168.1.0/24:*"] },
      # Implicit default deny for everything else
    ],
    # Auto-Approve the LAN route for the router tag
    "autoApprovers" : {
      "routes" : {
        "192.168.1.0/24" : ["tag:cluster-subnet-router"],
      },
    },
  })
}
