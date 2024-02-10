resource "cloudflare_ruleset" "common_ruleset" {
  zone_id = local.zone_id
  name    = "Common Firewall Ruleset"
  kind    = "zone"
  phase   = "http_request_firewall_custom"

  rules {
    action      = "block"
    expression  = "cf.client.bot"
    description = "Block bots determined by CF"
  }

  rules {
    action      = "block"
    expression  = "cf.threat_score > 14"
    description = "Block medium threats and higher"
  }
}
