resource "tailscale_dns_split_nameservers" "homelab" {
  domain      = "edgard.org"
  nameservers = ["192.168.1.1"]
}
