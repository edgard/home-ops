output "zone_id" {
  description = "Cloudflare Zone ID"
  value       = var.zone_id
}

output "firewall_ruleset_id" {
  description = "Firewall Ruleset ID"
  value       = cloudflare_ruleset.firewall_rules.id
}

output "rate_limit_ruleset_id" {
  description = "Rate Limiting Ruleset ID"
  value       = cloudflare_ruleset.rate_limit_auth.id
}

