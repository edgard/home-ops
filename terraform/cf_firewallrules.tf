resource "cloudflare_filter" "common_filters" {
  for_each    = local.firewall_filters
  zone_id     = local.zone_id
  description = each.value.description
  expression  = each.value.expression
}

resource "cloudflare_firewall_rule" "common_rules" {
  for_each    = local.firewall_filters
  zone_id     = local.zone_id
  description = each.value.description
  filter_id   = cloudflare_filter.common_filters[each.key].id
  action      = "block"
}
