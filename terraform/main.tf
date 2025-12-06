terraform {
  # OpenTofu version - manually managed (Renovate disabled for terraform-version)
  required_version = ">= 1.10.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "5.14.0"
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

# Cloudflare Module
module "cloudflare" {
  source = "./cloudflare"

  zone_id = var.cloudflare_zone_id
}
