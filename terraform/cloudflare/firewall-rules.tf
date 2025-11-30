# Custom firewall rules using Cloudflare Rulesets (new API)
#
# NOTE: You currently have these rules active (managed outside Terraform):
# 1. "Block bots determined by CF" - cf.client.bot
# 2. "Block medium threats and higher" - cf.threat_score > 14
#
# These rules below complement your existing protections.

resource "cloudflare_ruleset" "firewall_rules" {
  zone_id     = var.zone_id
  name        = "Common Firewall Ruleset"
  description = "Terraform-managed firewall rules for edgard.org"
  kind        = "zone"
  phase       = "http_request_firewall_custom"

  # Rule 1: Block bots
  rules {
    action      = "block"
    expression  = "cf.client.bot"
    description = "Block bots determined by CF"
    enabled     = true
  }

  # Rule 2: Block high threat scores
  rules {
    action      = "block"
    expression  = "cf.threat_score > 14"
    description = "Block medium threats and higher"
    enabled     = true
  }

  # Rule 3: Challenge non-Polish traffic
  rules {
    action      = "managed_challenge"
    expression  = "(ip.geoip.country ne \"PL\")"
    description = "Challenge non-Polish traffic (allows legitimate users, adds friction for attackers)"
    enabled     = true
  }

  # Rule 4: Challenge unverified bots
  rules {
    action      = "managed_challenge"
    expression  = "(cf.client.bot and not cf.verified_bot_category in {\"Search Engine Crawler\" \"Monitoring & Analytics\" \"Aggregator\"})"
    description = "Challenge unverified bots (allows Google, etc.)"
    enabled     = true
  }
}
