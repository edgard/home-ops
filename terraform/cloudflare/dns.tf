# Static DNS records (not managed by external-dns or cert-manager)
# Note: tunnel.edgard.org is managed by external-dns via DNSEndpoint

# iCloud Mail - DKIM
resource "cloudflare_record" "dkim" {
  zone_id = var.zone_id
  name    = "sig1._domainkey"
  type    = "CNAME"
  content = "sig1.dkim.edgard.org.at.icloudmailadmin.com"
  proxied = false
  comment = "iCloud Mail DKIM"
}

# iCloud Mail - MX Records
resource "cloudflare_record" "mx_01" {
  zone_id  = var.zone_id
  name     = "edgard.org"
  type     = "MX"
  content  = "mx01.mail.icloud.com"
  priority = 10
  proxied  = false
  comment  = "iCloud Mail MX 1"
}

resource "cloudflare_record" "mx_02" {
  zone_id  = var.zone_id
  name     = "edgard.org"
  type     = "MX"
  content  = "mx02.mail.icloud.com"
  priority = 10
  proxied  = false
  comment  = "iCloud Mail MX 2"
}

# Email Security - SPF
resource "cloudflare_record" "spf" {
  zone_id = var.zone_id
  name    = "edgard.org"
  type    = "TXT"
  content = "v=spf1 include:icloud.com ~all"
  proxied = false
  comment = "SPF record for iCloud Mail"
}

# Email Security - DMARC
resource "cloudflare_record" "dmarc" {
  zone_id = var.zone_id
  name    = "_dmarc"
  type    = "TXT"
  content = "v=DMARC1; p=quarantine"
  proxied = false
  comment = "DMARC policy"
}

# Apple Domain Verification
resource "cloudflare_record" "apple_domain" {
  zone_id = var.zone_id
  name    = "edgard.org"
  type    = "TXT"
  content = "apple-domain=LKttxCr0jMIT8JCc"
  proxied = false
  comment = "Apple domain verification"
}
