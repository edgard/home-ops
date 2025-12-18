variable "cloudflare_zone_id" {
  description = "Cloudflare Zone ID for edgard.org"
  type        = string
  # Set via TF_VAR_cloudflare_zone_id environment variable
}

variable "tailscale_tailnet" {
  description = "Tailscale tailnet name"
  type        = string
  sensitive   = true
  # Set via TF_VAR_tailscale_tailnet environment variable
}

