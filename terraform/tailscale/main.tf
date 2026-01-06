terraform {
  required_providers {
    tailscale = {
      source  = "tailscale/tailscale"
      version = "0.25.0"
    }
  }
}

provider "tailscale" {
  # TAILSCALE_OAUTH_CLIENT_ID env var
  # TAILSCALE_OAUTH_CLIENT_SECRET env var
  tailnet = var.tailscale_tailnet
}
