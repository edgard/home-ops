# Cloudflare Teams Account Configuration
resource "cloudflare_teams_account" "edgard" {
  account_id           = local.account_id
  activity_log_enabled = false
  logging {
    redact_pii = false
    settings_by_rule_type {
      dns {
        log_all    = false
        log_blocks = false
      }
      http {
        log_all    = false
        log_blocks = false
      }
      l4 {
        log_all    = false
        log_blocks = false
      }
    }
  }
  proxy {
    tcp = true
    udp = true
  }
  lifecycle {
    prevent_destroy = true
  }
}

# Argo Tunnel Configuration
resource "cloudflare_argo_tunnel" "home" {
  account_id = local.account_id
  name       = local.tunnel_name
  secret     = local.tunnel_secret
  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_tunnel_route" "home_lan" {
  account_id = local.account_id
  tunnel_id  = cloudflare_argo_tunnel.home.id
  network    = local.lan_cidr
  comment    = "Home LAN"
}

# Split Tunnel and Fallback Domain Configuration
resource "cloudflare_split_tunnel" "home_lan_include" {
  account_id = local.account_id
  mode       = "include"
  tunnels {
    address     = local.lan_cidr
    description = "Home LAN"
  }
  tunnels {
    host        = local.private_domain
    description = "Home Domain"
  }
}

resource "cloudflare_fallback_domain" "home_lan" {
  account_id = local.account_id
  domains {
    suffix      = local.private_domain
    description = "Home LAN"
    dns_server  = [cidrhost(local.lan_cidr, 1)]
  }
  dynamic "domains" {
    for_each = toset(["corp", "domain", "home", "host", "internal", "intranet", "invalid", "lan", "local", "localdomain", "localhost", "private", "test"])
    content {
      suffix = domains.value
    }
  }
}

# Access and Identity Configuration
resource "cloudflare_access_identity_provider" "otp" {
  account_id = local.account_id
  name       = "OTP"
  type       = "onetimepin"
}

resource "cloudflare_access_group" "users" {
  account_id = local.account_id
  name       = "Users"
  include {
    email = local.users_group_emails
  }
}

# Applications and Policies Configuration
resource "cloudflare_record" "root_cname_home_apps" {
  for_each = { for app in local.cloudflare_apps : app.name => app }
  name     = each.value.name
  proxied  = true
  ttl      = 1
  type     = "CNAME"
  value    = "${cloudflare_argo_tunnel.home.id}.cfargotunnel.com"
  zone_id  = local.zone_id
}

resource "cloudflare_access_application" "http_home_apps" {
  for_each                  = { for app in local.cloudflare_apps : app.name => app }
  account_id                = local.account_id
  name                      = each.value.name
  domain                    = "${each.value.name}.${local.public_domain}"
  session_duration          = "730h"
  auto_redirect_to_identity = true
  allowed_idps              = [cloudflare_access_identity_provider.otp.id]
}

resource "cloudflare_access_policy" "http_home_apps_allow" {
  for_each       = toset([for app in local.cloudflare_apps : app.name if app.auth == true])
  account_id     = local.account_id
  application_id = cloudflare_access_application.http_home_apps[each.value].id
  name           = "${each.value} allow"
  precedence     = "1"
  decision       = "allow"

  include {
    login_method = [cloudflare_access_identity_provider.otp.id]
  }
  require {
    group = [cloudflare_access_group.users.id]
  }
}

resource "cloudflare_access_policy" "http_home_apps_bypass" {
  for_each       = toset([for app in local.cloudflare_apps : app.name if app.auth == false])
  account_id     = local.account_id
  application_id = cloudflare_access_application.http_home_apps[each.value].id
  name           = "${each.value} bypass"
  precedence     = "1"
  decision       = "bypass"

  include {
    everyone = true
  }
}
