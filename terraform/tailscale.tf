provider "tailscale" {
  oauth_client_id     = var.tailscale_client_id
  oauth_client_secret = var.tailscale_client_secret
  tailnet             = "-"
}

resource "tailscale_dns_preferences" "config" {
  magic_dns = true
}

resource "tailscale_dns_split_nameservers" "edgard_org" {
  domain      = "edgard.org"
  nameservers = ["192.168.1.1"]
}

resource "tailscale_acl" "policy" {
  acl = jsonencode({
    "tagOwners" : {
      "tag:k8s-router" : ["autogroup:admin"],
    },
    "acls" : [
      { "action" : "accept", "src" : ["*"], "dst" : ["192.168.1.241:80", "192.168.1.241:443"] },
      { "action" : "accept", "src" : ["*"], "dst" : ["192.168.1.1:53"] },
    ],
    "autoApprovers" : {
      "routes" : {
        "192.168.1.241/32" : ["tag:k8s-router"],
        "192.168.1.1/32" : ["tag:k8s-router"],
      },
    },
  })
}
