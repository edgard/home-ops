terraform {
  # OpenTofu version - manually managed (Renovate disabled for terraform-version)
  required_version = ">= 1.10.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "5.13.0"
    }
  }

  backend "s3" {
    bucket = "terraform-state"
    key    = "homelab/terraform.tfstate"
    region = "auto"

    # R2 endpoint
    endpoints = {
      s3 = "https://0e9cad60bb63ebd8559dddda9be29bc3.r2.cloudflarestorage.com"
    }

    # Required for R2
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
  }
}

provider "cloudflare" {
  # Reads from CLOUDFLARE_API_TOKEN environment variable
}

# Cloudflare Module
module "cloudflare" {
  source = "./cloudflare"

  zone_id = var.cloudflare_zone_id
}
