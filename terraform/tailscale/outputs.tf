output "split_dns_domain" {
  description = "Domain configured for split DNS in Tailscale"
  value       = tailscale_dns_split_nameservers.homelab.domain
}

output "split_dns_nameservers" {
  description = "Nameservers for split DNS domain"
  value       = tailscale_dns_split_nameservers.homelab.nameservers
}
