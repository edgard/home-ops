# Static DNS records for Cloudflare (public DNS)
# Note: These same records are mirrored in Unifi DNS via external-dns DNSEndpoints for split-DNS

# iCloud Mail - DKIM
resource "cloudflare_dns_record" "dkim" {
  zone_id = var.zone_id
  name    = "sig1._domainkey"
  type    = "CNAME"
  content = "sig1.dkim.edgard.org.at.icloudmailadmin.com"
  ttl     = 3600
  proxied = false
  comment = "iCloud Mail DKIM"
}

# iCloud Mail - MX Records
resource "cloudflare_dns_record" "mx_01" {
  zone_id  = var.zone_id
  name     = "edgard.org"
  type     = "MX"
  content  = "mx01.mail.icloud.com"
  priority = 10
  ttl      = 3600
  proxied  = false
  comment  = "iCloud Mail MX 1"
}

resource "cloudflare_dns_record" "mx_02" {
  zone_id  = var.zone_id
  name     = "edgard.org"
  type     = "MX"
  content  = "mx02.mail.icloud.com"
  priority = 10
  ttl      = 3600
  proxied  = false
  comment  = "iCloud Mail MX 2"
}

# Email Security - SPF
resource "cloudflare_dns_record" "spf" {
  zone_id = var.zone_id
  name    = "edgard.org"
  type    = "TXT"
  content = "v=spf1 include:icloud.com ~all"
  ttl     = 3600
  proxied = false
  comment = "iCloud Mail SPF"
}

# Email Security - DMARC
resource "cloudflare_dns_record" "dmarc" {
  zone_id = var.zone_id
  name    = "_dmarc"
  type    = "TXT"
  content = "v=DMARC1; p=quarantine"
  ttl     = 3600
  proxied = false
  comment = "iCloud Mail DMARC"
}

# Apple Domain Verification
resource "cloudflare_dns_record" "apple_domain" {
  zone_id = var.zone_id
  name    = "edgard.org"
  type    = "TXT"
  content = "apple-domain=LKttxCr0jMIT8JCc"
  ttl     = 3600
  proxied = false
  comment = "Apple Domain Verification"
}

# GitHub Pages - A Records
resource "cloudflare_dns_record" "github_pages_a_01" {
  zone_id = var.zone_id
  name    = "edgard.org"
  type    = "A"
  content = "185.199.108.153"
  ttl     = 1
  proxied = false
  comment = "GitHub Pages A record 1"
}

resource "cloudflare_dns_record" "github_pages_a_02" {
  zone_id = var.zone_id
  name    = "edgard.org"
  type    = "A"
  content = "185.199.109.153"
  ttl     = 1
  proxied = false
  comment = "GitHub Pages A record 2"
}

resource "cloudflare_dns_record" "github_pages_a_03" {
  zone_id = var.zone_id
  name    = "edgard.org"
  type    = "A"
  content = "185.199.110.153"
  ttl     = 1
  proxied = false
  comment = "GitHub Pages A record 3"
}

resource "cloudflare_dns_record" "github_pages_a_04" {
  zone_id = var.zone_id
  name    = "edgard.org"
  type    = "A"
  content = "185.199.111.153"
  ttl     = 1
  proxied = false
  comment = "GitHub Pages A record 4"
}

# GitHub Pages - WWW CNAME
resource "cloudflare_dns_record" "github_pages_www" {
  zone_id = var.zone_id
  name    = "www"
  type    = "CNAME"
  content = "edgard.github.io"
  ttl     = 1
  proxied = false
  comment = "GitHub Pages WWW subdomain"
}
