# letsencrypt certificate authority record
resource "cloudflare_record" "root_caa" {
  name    = data.sops_file.terraform_secrets.data["public_domain"]
  proxied = false
  ttl     = 1
  type    = "CAA"
  zone_id = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
  data {
    flags = 0
    tag   = "issue"
    value = "letsencrypt.org"
  }
}

# email records
resource "cloudflare_record" "root_dkim_fm1" {
  name    = "fm1._domainkey"
  proxied = false
  ttl     = 1
  type    = "CNAME"
  value   = "fm1.${data.sops_file.terraform_secrets.data["public_domain"]}.dkim.fmhosted.com"
  zone_id = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
}

resource "cloudflare_record" "root_dkim_fm2" {
  name    = "fm2._domainkey"
  proxied = false
  ttl     = 1
  type    = "CNAME"
  value   = "fm2.${data.sops_file.terraform_secrets.data["public_domain"]}.dkim.fmhosted.com"
  zone_id = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
}

resource "cloudflare_record" "root_dkim_fm3" {
  name    = "fm3._domainkey"
  proxied = false
  ttl     = 1
  type    = "CNAME"
  value   = "fm3.${data.sops_file.terraform_secrets.data["public_domain"]}.dkim.fmhosted.com"
  zone_id = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
}

resource "cloudflare_record" "root_mx1" {
  name     = data.sops_file.terraform_secrets.data["public_domain"]
  priority = 10
  proxied  = false
  ttl      = 1
  type     = "MX"
  value    = "in1-smtp.messagingengine.com"
  zone_id  = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
}

resource "cloudflare_record" "root_mx2" {
  name     = data.sops_file.terraform_secrets.data["public_domain"]
  priority = 20
  proxied  = false
  ttl      = 1
  type     = "MX"
  value    = "in2-smtp.messagingengine.com"
  zone_id  = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
}

resource "cloudflare_record" "root_wildcard_mx1" {
  name     = "*"
  priority = 10
  proxied  = false
  ttl      = 1
  type     = "MX"
  value    = "in1-smtp.messagingengine.com"
  zone_id  = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
}

resource "cloudflare_record" "root_wildcard_mx2" {
  name     = "*"
  priority = 20
  proxied  = false
  ttl      = 1
  type     = "MX"
  value    = "in2-smtp.messagingengine.com"
  zone_id  = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
}

resource "cloudflare_record" "root_dmarc" {
  name    = "_dmarc"
  proxied = false
  ttl     = 1
  type    = "TXT"
  value   = "v=DMARC1; p=quarantine; rua=mailto:${data.sops_file.terraform_secrets.data["email"]}"
  zone_id = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
}

resource "cloudflare_record" "root_spf" {
  name    = data.sops_file.terraform_secrets.data["public_domain"]
  proxied = false
  ttl     = 1
  type    = "TXT"
  value   = "v=spf1 include:spf.messagingengine.com ?all"
  zone_id = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
}

# other records
resource "cloudflare_record" "root_cname" {
  name    = data.sops_file.terraform_secrets.data["public_domain"]
  proxied = true
  ttl     = 1
  type    = "CNAME"
  value   = data.sops_file.terraform_secrets.data["homepage"]
  zone_id = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
}

resource "cloudflare_record" "root_cname_www" {
  name    = "www"
  proxied = true
  ttl     = 1
  type    = "CNAME"
  value   = data.sops_file.terraform_secrets.data["homepage"]
  zone_id = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
}
