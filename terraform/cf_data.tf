data "cloudflare_zones" "public_domain" {
  filter {
    name = local.public_domain
  }
}
