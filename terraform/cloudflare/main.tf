# Cloudflare module - called from root terraform/main.tf
# This file defines the Cloudflare resources but doesn't configure backend/providers

terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

