data "cloudflare_zones" "public_domain" {
  filter {
    name = data.sops_file.terraform_secrets.data["public_domain"]
  }
}
