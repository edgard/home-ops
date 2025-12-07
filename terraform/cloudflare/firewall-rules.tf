# Custom firewall rules using Cloudflare Rulesets (new API)

resource "cloudflare_ruleset" "firewall_rules" {
  zone_id     = var.zone_id
  name        = "Common Firewall Ruleset"
  description = "Terraform-managed firewall rules for edgard.org"
  kind        = "zone"
  phase       = "http_request_firewall_custom"

  rules = [
    # Rule 1: Block bots
    {
      action      = "block"
      expression  = "cf.client.bot"
      description = "Block bots determined by CF"
      enabled     = true
    },
    # Rule 2: Block empty user agents
    {
      action      = "block"
      expression  = "len(http.user_agent) == 0"
      description = "Block requests with empty user agent"
      enabled     = true
    },
    # Rule 3: Challenge non-Polish traffic
    {
      action      = "managed_challenge"
      expression  = "(ip.geoip.country ne \"PL\")"
      description = "Challenge non-Polish traffic (allows legitimate users, adds friction for attackers)"
      enabled     = true
    }
  ]
}
