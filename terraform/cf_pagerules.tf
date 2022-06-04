resource "cloudflare_page_rule" "plex_bypass_cache" {
  zone_id = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
  target  = "plex.${data.sops_file.terraform_secrets.data["public_domain"]}/*"
  status  = "active"

  actions {
    cache_level = "bypass"
  }
}
