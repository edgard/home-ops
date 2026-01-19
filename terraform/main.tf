terraform {
  # OpenTofu version - manually managed (Renovate disabled for terraform-version)
  required_version = ">= 1.10.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "5.15.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "3.0.1"
    }
    tailscale = {
      source  = "tailscale/tailscale"
      version = "0.16.1"
    }
    bitwarden-secrets = {
      source  = "bitwarden/bitwarden-secrets"
      version = "0.5.4-pre"
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

provider "bitwarden-secrets" {
  api_url         = "https://api.bitwarden.com"
  identity_url    = "https://identity.bitwarden.com"
  organization_id = var.bitwarden_org_id
}

# --- Bitwarden Secrets Lookups ---

data "bitwarden-secrets_secret" "cloudflare_token" {
  id = var.bw_secret_ids["cloudflare_token"]
}

data "bitwarden-secrets_secret" "cloudflare_zone_id" {
  id = var.bw_secret_ids["cloudflare_zone_id"]
}

data "bitwarden-secrets_secret" "tailscale_client_id" {
  id = var.bw_secret_ids["tailscale_client_id"]
}

data "bitwarden-secrets_secret" "tailscale_client_secret" {
  id = var.bw_secret_ids["tailscale_client_secret"]
}

# --- Provider Configurations ---

provider "cloudflare" {
  api_token = data.bitwarden-secrets_secret.cloudflare_token.value
}

provider "kubernetes" {
  # Reads from KUBECONFIG environment variable or ~/.kube/config
  config_path = "~/.kube/config"
}

# --- Modules ---

# Cloudflare Module
module "cloudflare" {
  source = "./cloudflare"

  # Uses the secret retrieved from Bitwarden
  zone_id = data.bitwarden-secrets_secret.cloudflare_zone_id.value
}
