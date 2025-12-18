output "zone_id" {
  description = "Cloudflare Zone ID"
  value       = var.zone_id
}

output "firewall_ruleset_id" {
  description = "Firewall Ruleset ID"
  value       = cloudflare_ruleset.firewall_rules.id
}

