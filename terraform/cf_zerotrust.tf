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
}

# argo tunnel
resource "random_string" "home_tunnel_secret" {
  length = 32
}

resource "cloudflare_argo_tunnel" "home" {
  account_id = data.sops_file.terraform_secrets.data["cloudflare_account_id"]
  name       = "home"
  secret     = base64encode(random_string.home_tunnel_secret.result)
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
    email = nonsensitive({ for x in yamldecode(data.sops_file.terraform_secrets.raw).auth_groups : x.name => x if x.name == "Users" })["Users"].emails
  }
}

# access: kubernetes ingresses
resource "cloudflare_record" "root_cname_home_k8s" {
  for_each = nonsensitive({ for x in yamldecode(data.sops_file.terraform_secrets.raw).k8s_ingresses : x.name => x })
  name     = each.value.name
  proxied  = true
  ttl      = 1
  type     = "CNAME"
  value    = "${cloudflare_argo_tunnel.home.id}.cfargotunnel.com"
  zone_id  = lookup(data.cloudflare_zones.public_domain.zones[0], "id")
}

# access: kubernetes ingresses rpz
resource "dns_a_record_set" "rpz_a_records" {
  for_each  = nonsensitive({ for x in yamldecode(data.sops_file.terraform_secrets.raw).k8s_ingresses : x.name => x })
  zone      = "rpz."
  name      = format("%s.%s", each.value.name, data.sops_file.terraform_secrets.data["public_domain"])
  addresses = [data.sops_file.terraform_secrets.data["k8s_ingress_ip"]]
  ttl       = 300
}

# access: kubernetes ingresses applications and policies
resource "cloudflare_access_application" "http_home_k8s" {
  for_each                  = nonsensitive({ for x in yamldecode(data.sops_file.terraform_secrets.raw).k8s_ingresses : x.name => x })
  account_id                = data.sops_file.terraform_secrets.data["cloudflare_account_id"]
  name                      = each.value.name
  domain                    = "${each.value.name}.${data.sops_file.terraform_secrets.data["public_domain"]}"
  session_duration          = "730h"
  auto_redirect_to_identity = true
  allowed_idps              = [cloudflare_access_identity_provider.otp.id]
}

resource "cloudflare_access_policy" "http_home_k8s_allow" {
  for_each       = nonsensitive(toset([for x in yamldecode(data.sops_file.terraform_secrets.raw).k8s_ingresses : x.name if x.require_auth == true]))
  account_id     = data.sops_file.terraform_secrets.data["cloudflare_account_id"]
  application_id = cloudflare_access_application.http_home_k8s[each.value].id
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

resource "cloudflare_access_policy" "http_home_k8s_bypass" {
  for_each       = nonsensitive(toset([for x in yamldecode(data.sops_file.terraform_secrets.raw).k8s_ingresses : x.name if x.require_auth == false]))
  account_id     = data.sops_file.terraform_secrets.data["cloudflare_account_id"]
  application_id = cloudflare_access_application.http_home_k8s[each.value].id
  name           = "${each.value} bypass"
  precedence     = "1"
  decision       = "bypass"

  include {
    everyone = true
  }
}

# access: photoprism-import application for path bypass while cf doesn't offer a way to better do this
resource "cloudflare_access_application" "http_home_k8s_photoprism_import" {
  account_id = data.sops_file.terraform_secrets.data["cloudflare_account_id"]
  name       = "photoprism-import"
  domain     = "photoprism.${data.sops_file.terraform_secrets.data["public_domain"]}/import/*"
}

resource "cloudflare_access_policy" "http_home_k8s_photoprism_import_bypass" {
  account_id     = data.sops_file.terraform_secrets.data["cloudflare_account_id"]
  application_id = cloudflare_access_application.http_home_k8s_photoprism_import.id
  name           = "photoprism-import bypass"
  precedence     = "1"
  decision       = "bypass"

  include {
    everyone = true
  }
}

# output tunnel info
output "cf_home_tunnel_id" {
  value = cloudflare_argo_tunnel.home.id
}

output "cf_home_tunnel_secret" {
  value = base64encode(random_string.home_tunnel_secret.result)
}
