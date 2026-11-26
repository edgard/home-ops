variable "private_access" {
  description = "Exact browser identity and per-installation Cloudflare service token resource IDs, supplied in private-access.auto.tfvars.json."
  type = object({
    karakeep_email     = string
    karakeep_token_ids = set(string)
    atuin_token_ids    = set(string)
  })
  nullable = false
  validation {
    condition = can(regex("^[^ *@]+@[^ *@]+[.][^ *@]+$", var.private_access.karakeep_email)) && length(setintersection(var.private_access.karakeep_token_ids, var.private_access.atuin_token_ids)) == 0 && alltrue([
      for id in setunion(var.private_access.karakeep_token_ids, var.private_access.atuin_token_ids) : can(regex("^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$", id))
    ])
    error_message = "Supply one exact email and disjoint sets of lowercase service token UUIDs for the two applications."
  }
}

locals {
  private_apps = {
    atuin    = var.private_access.atuin_token_ids
    karakeep = var.private_access.karakeep_token_ids
  }
  # Publish individually after the connector and protected origins are verified.
  published_apps = toset(["atuin", "karakeep"])
  # Add an app here to disable its origin before withdrawing DNS.
  suspended_apps    = toset([])
  access_account_id = data.cloudflare_zone.home_ops.account.id
}

data "cloudflare_zone" "home_ops" {
  zone_id = var.cloudflare_zone_id
}

data "cloudflare_zero_trust_organization" "home_ops" {
  account_id = local.access_account_id
}

resource "cloudflare_zero_trust_access_identity_provider" "email_pin" {
  account_id = local.access_account_id
  name       = "Home ops email PIN"
  type       = "onetimepin"
  config     = {}
}

resource "cloudflare_zero_trust_access_policy" "browser" {
  account_id = local.access_account_id
  name       = "Karakeep browser"
  decision   = "allow"
  include    = [{ email = { email = var.private_access.karakeep_email } }]
  mfa_config = {
    allowed_authenticators = ["biometrics", "security_key"]
    session_duration       = "24h"
    mfa_disabled           = false
  }
}

resource "cloudflare_zero_trust_access_policy" "clients" {
  for_each   = { for app, ids in local.private_apps : app => ids if length(ids) > 0 }
  account_id = local.access_account_id
  name       = "${each.key} clients"
  decision   = "non_identity"
  include    = [for id in each.value : { service_token = { token_id = id } }]
}

resource "cloudflare_zero_trust_access_application" "app" {
  for_each                    = local.private_apps
  account_id                  = local.access_account_id
  name                        = each.key
  type                        = "self_hosted"
  domain                      = "${each.key}.edgard.org"
  session_duration            = "24h"
  allowed_idps                = [cloudflare_zero_trust_access_identity_provider.email_pin.id]
  allow_authenticate_via_warp = false
  service_auth_401_redirect   = each.key == "atuin"
  policies = concat(
    length(each.value) > 0 ? [{ id = cloudflare_zero_trust_access_policy.clients[each.key].id, precedence = 1 }] : [],
    each.key == "karakeep" ? [{ id = cloudflare_zero_trust_access_policy.browser.id, precedence = 2 }] : []
  )
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "home_ops" {
  account_id = local.access_account_id
  name       = "home-ops"
  config_src = "cloudflare"
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "home_ops" {
  account_id = local.access_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.home_ops.id
  config = {
    ingress = concat([for app, application in cloudflare_zero_trust_access_application.app : {
      hostname = application.domain
      service  = "https://envoy-platform-system-gateway-78128755.platform-system.svc.cluster.local:443"
      origin_request = {
        origin_server_name = application.domain
        http_host_header   = application.domain
        access = {
          required  = true
          team_name = trimsuffix(data.cloudflare_zero_trust_organization.home_ops.auth_domain, ".cloudflareaccess.com")
          aud_tag   = [application.aud]
        }
      }
    } if !contains(local.suspended_apps, app)], [{ service = "http_status:404" }])
  }
}

resource "cloudflare_dns_record" "private_apps" {
  for_each   = local.published_apps
  zone_id    = var.cloudflare_zone_id
  name       = cloudflare_zero_trust_access_application.app[each.key].domain
  type       = "CNAME"
  content    = "${cloudflare_zero_trust_tunnel_cloudflared.home_ops.id}.cfargotunnel.com"
  proxied    = true
  ttl        = 1
  depends_on = [cloudflare_zero_trust_tunnel_cloudflared_config.home_ops]

  lifecycle {
    precondition {
      condition     = contains(local.suspended_apps, each.key) || length(local.private_apps[each.key]) > 0
      error_message = "Enroll an application-specific client before publishing DNS."
    }
    precondition {
      condition = contains(local.suspended_apps, each.key) || each.key != "karakeep" || try(length(setintersection(
        toset(data.cloudflare_zero_trust_organization.home_ops.mfa_config.allowed_authenticators),
        toset(["biometrics", "security_key"])
      )) > 0, false)
      error_message = "Enable independent WebAuthn MFA in the Zero Trust organization before publishing Karakeep."
    }
  }
}
