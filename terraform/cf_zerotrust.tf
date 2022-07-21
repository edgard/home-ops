# teams account
resource "cloudflare_teams_account" "edgard" {
  account_id           = data.sops_file.terraform_secrets.data["cloudflare_account_id"]
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

# argo tunnel
resource "cloudflare_argo_tunnel" "home" {
  account_id = data.sops_file.terraform_secrets.data["cloudflare_account_id"]
  name       = data.sops_file.terraform_secrets.data["cloudflare_tunnel_name"]
  secret     = data.sops_file.terraform_secrets.data["cloudflare_tunnel_secret"]
  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_tunnel_route" "home_lan" {
  account_id = data.sops_file.terraform_secrets.data["cloudflare_account_id"]
  tunnel_id  = cloudflare_argo_tunnel.home.id
  network    = data.sops_file.terraform_secrets.data["lan_cidr"]
  comment    = "Home LAN"
}

resource "cloudflare_split_tunnel" "home_lan_include" {
  account_id = data.sops_file.terraform_secrets.data["cloudflare_account_id"]
  mode       = "include"
  tunnels {
    address     = data.sops_file.terraform_secrets.data["lan_cidr"]
    description = "Home LAN"
  }
  tunnels {
    host        = data.sops_file.terraform_secrets.data["private_domain"]
    description = "Home Domain"
  }
}

resource "cloudflare_fallback_domain" "home_lan" {
  account_id = data.sops_file.terraform_secrets.data["cloudflare_account_id"]
  domains {
    suffix      = data.sops_file.terraform_secrets.data["private_domain"]
    description = "Home LAN"
    dns_server  = [data.sops_file.terraform_secrets.data["dns_server_ip"]]
  }
  dynamic "domains" {
    for_each = toset(["corp", "domain", "home", "host", "internal", "intranet", "invalid", "lan", "local", "localdomain", "localhost", "private", "test"])
    content {
      suffix = domains.value
    }
  }
}

# access: idp
resource "cloudflare_access_identity_provider" "otp" {
  account_id = data.sops_file.terraform_secrets.data["cloudflare_account_id"]
  name       = "OTP"
  type       = "onetimepin"
}

# access: groups
resource "cloudflare_access_group" "users" {
  account_id = data.sops_file.terraform_secrets.data["cloudflare_account_id"]
  name       = "Users"
  include {
    email = nonsensitive({ for x in yamldecode(data.sops_file.terraform_secrets.raw).cloudflare_auth_groups : x.name => x if x.name == "Users" })["Users"].emails
  }
}

# access: applications
resource "cloudflare_record" "root_cname_home_apps" {
  for_each = nonsensitive({ for x in yamldecode(data.sops_file.terraform_secrets.raw).apps : x.name => x })
  name     = each.value.name
  proxied  = true
  ttl      = 1
  type     = "CNAME"
  value    = "${cloudflare_argo_tunnel.home.id}.cfargotunnel.com"
  zone_id  = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
}

resource "cloudflare_access_application" "http_home_apps" {
  for_each                  = nonsensitive({ for x in yamldecode(data.sops_file.terraform_secrets.raw).apps : x.name => x })
  account_id                = data.sops_file.terraform_secrets.data["cloudflare_account_id"]
  name                      = each.value.name
  domain                    = "${each.value.name}.${data.sops_file.terraform_secrets.data["public_domain"]}"
  session_duration          = "730h"
  auto_redirect_to_identity = true
  allowed_idps              = [cloudflare_access_identity_provider.otp.id]
}

resource "cloudflare_access_policy" "http_home_apps_allow" {
  for_each       = nonsensitive(toset([for x in yamldecode(data.sops_file.terraform_secrets.raw).apps : x.name if x.require_auth == true]))
  account_id     = data.sops_file.terraform_secrets.data["cloudflare_account_id"]
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
  for_each       = nonsensitive(toset([for x in yamldecode(data.sops_file.terraform_secrets.raw).apps : x.name if x.require_auth == false]))
  account_id     = data.sops_file.terraform_secrets.data["cloudflare_account_id"]
  application_id = cloudflare_access_application.http_home_apps[each.value].id
  name           = "${each.value} bypass"
  precedence     = "1"
  decision       = "bypass"

  include {
    everyone = true
  }
}
