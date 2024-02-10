terraform {
  required_providers {
    null = {
      source  = "hashicorp/null"
      version = ">= 3.2.2"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = ">= 4.24.0"
    }
    sops = {
      source  = "carlpett/sops"
      version = ">= 1.0.0"
    }
  }
  required_version = ">= 1.1.9"
}

data "sops_file" "terraform_secrets" {
  source_file = "../config.sops.yaml"
}

provider "cloudflare" {
  email   = local.email
  api_key = local.api_key
}
