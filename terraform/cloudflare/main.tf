# Cloudflare module - called from root terraform/main.tf
# Provider version is defined in root terraform/main.tf

terraform {
  required_providers {
    cloudflare = {
      source = "cloudflare/cloudflare"
    }
  }
}
