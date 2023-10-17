locals {
  # Cloudflare general settings
  api_key    = data.sops_file.terraform_secrets.data["cloudflare_api_key"]
  account_id = data.sops_file.terraform_secrets.data["cloudflare_account_id"]
  zone_id    = lookup(data.cloudflare_zones.public_domain.zones[0], "id")

  # Domain settings
  public_domain  = data.sops_file.terraform_secrets.data["public_domain"]
  private_domain = data.sops_file.terraform_secrets.data["private_domain"]

  # Email and homepage settings
  email    = data.sops_file.terraform_secrets.data["email"]
  homepage = data.sops_file.terraform_secrets.data["homepage"]

  # Cloudflare tunnel settings
  tunnel_name   = data.sops_file.terraform_secrets.data["cloudflare_tunnel_name"]
  tunnel_secret = data.sops_file.terraform_secrets.data["cloudflare_tunnel_secret"]

  # Local network settings
  lan_cidr = data.sops_file.terraform_secrets.data["lan_cidr"]

  # Cloudflare apps and auth groups
  cloudflare_apps        = nonsensitive(yamldecode(data.sops_file.terraform_secrets.raw).cloudflare_apps)
  cloudflare_auth_groups = nonsensitive(yamldecode(data.sops_file.terraform_secrets.raw).cloudflare_auth_groups)
  users_group_emails     = flatten([for group in local.cloudflare_auth_groups : group.emails if group.name == "Users"])

  # Firewall filter settings
  firewall_filters = {
    bots = {
      description = "Block bots determined by CF"
      expression  = "(cf.client.bot)"
    },
    threats = {
      description = "Block medium threats and higher"
      expression  = "(cf.threat_score gt 14)"
    }
  }
}
