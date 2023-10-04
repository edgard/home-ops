terraform {
  required_providers {
    null = {
      source  = "hashicorp/null"
      version = ">= 3.1.1"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = ">= 3.16.0"
    }
    sops = {
      source  = "carlpett/sops"
      version = ">= 0.7.1"
    }
  }
  required_version = ">= 1.1.9"
}

data "sops_file" "terraform_secrets" {
  source_file = "secrets.sops.yaml"
}

provider "cloudflare" {
  email   = data.sops_file.terraform_secrets.data["email"]
  api_key = data.sops_file.terraform_secrets.data["cloudflare_api_key"]
}
