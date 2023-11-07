# LetsEncrypt Certificate Authority Record
resource "cloudflare_record" "root_caa" {
  name    = local.public_domain
  proxied = false
  ttl     = 1
  type    = "CAA"
  zone_id = local.zone_id
  data {
    flags = 0
    tag   = "issue"
    value = "letsencrypt.org"
  }
}

# Email Records
resource "cloudflare_record" "root_dkim" {
  for_each = toset(["sig1"])
  name     = "${each.value}._domainkey"
  proxied  = false
  ttl      = 1
  type     = "CNAME"
  value    = format("%s.dkim.%s.at.icloudmailadmin.com", each.value, local.public_domain)
  zone_id  = local.zone_id
}

resource "cloudflare_record" "root_mx" {
  for_each = tomap({ "mx01.mail.icloud.com" = "10", "mx02.mail.icloud.com" = "10" })
  name     = local.public_domain
  priority = each.value
  proxied  = false
  ttl      = 1
  type     = "MX"
  value    = each.key
  zone_id  = local.zone_id
}

resource "cloudflare_record" "root_spf" {
  name    = local.public_domain
  proxied = false
  ttl     = 1
  type    = "TXT"
  value   = "v=spf1 include:icloud.com ~all"
  zone_id = local.zone_id
}

resource "cloudflare_record" "root_dmarc" {
  name    = "_dmarc"
  proxied = false
  ttl     = 1
  type    = "TXT"
  value   = format("v=DMARC1; p=quarantine; rua=mailto:%s", local.email)
  zone_id = local.zone_id
}

# Other Records
resource "cloudflare_record" "root_cname" {
  name    = local.public_domain
  proxied = true
  ttl     = 1
  type    = "CNAME"
  value   = local.homepage
  zone_id = local.zone_id
}

resource "cloudflare_record" "root_cname_www" {
  name    = "www"
  proxied = true
  ttl     = 1
  type    = "CNAME"
  value   = local.homepage
  zone_id = local.zone_id
}
