terraform {
  # OpenTofu version - manually managed (Renovate disabled for terraform-version)
  required_version = ">= 1.10.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "5.15.0"
    }
    tailscale = {
      source  = "tailscale/tailscale"
      version = "0.24.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "3.0.1"
    }
  }

  backend "s3" {
    bucket = "shadowhausterraform"
    key    = "homelab/terraform.tfstate"
    region = "eu-central-003"

    # Backblaze B2 S3-compatible endpoint (EU)
    endpoints = {
      s3 = "https://s3.eu-central-003.backblazeb2.com"
    }

    # Required for B2
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
  }
}

provider "cloudflare" {
  # Reads from CLOUDFLARE_API_TOKEN environment variable
}

provider "tailscale" {
  # Reads from TAILSCALE_OAUTH_CLIENT_ID and TAILSCALE_OAUTH_CLIENT_SECRET environment variables
}

provider "kubernetes" {
  # Reads from KUBECONFIG environment variable or ~/.kube/config
  config_path = "~/.kube/config"
}

# Cloudflare Module
module "cloudflare" {
  source = "./cloudflare"

  zone_id = var.cloudflare_zone_id
}

# Tailscale Module
module "tailscale" {
  source = "./tailscale"

  tailscale_tailnet = var.tailscale_tailnet
}
