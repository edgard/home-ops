# bots
resource "cloudflare_filter" "bots" {
  zone_id     = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
  description = "Block bots determined by CF"
  expression  = "(cf.client.bot)"
}

resource "cloudflare_firewall_rule" "bots" {
  zone_id     = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
  description = "Block bots determined by CF"
  filter_id   = cloudflare_filter.bots.id
  action      = "block"
}

# block medium threats and higher
resource "cloudflare_filter" "threats" {
  zone_id     = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
  description = "Block medium threats and higher"
  expression  = "(cf.threat_score gt 14)"
}

resource "cloudflare_firewall_rule" "threats" {
  zone_id     = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
  description = "Block medium threats and higher"
  filter_id   = cloudflare_filter.threats.id
  action      = "block"
}
