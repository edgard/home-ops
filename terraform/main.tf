terraform {
  # OpenTofu version - manually managed (Renovate excludes Terraform CLI versions)
  required_version = ">= 1.10.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "5.27.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "3.3.0"
    }
    tailscale = {
      source  = "tailscale/tailscale"
      version = "0.29.2"
    }
  }

  backend "s3" {
    bucket = "shadowhausterraform"
    key    = "homelab/terraform.tfstate"
    region = "eu-central-003"

    # B2 needs its regional S3 endpoint and skips unsupported AWS validations.
    endpoints = {
      s3 = "https://s3.eu-central-003.backblazeb2.com"
    }

    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

provider "kubernetes" {
  config_path = "~/.kube/config"
}

module "cloudflare" {
  source = "./cloudflare"

  zone_id = var.cloudflare_zone_id
}
