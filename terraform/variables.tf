variable "cloudflare_api_token" {
  description = "Cloudflare API token"
  type        = string
  sensitive   = true
  nullable    = false
  validation {
    condition     = length(var.cloudflare_api_token) > 0
    error_message = "cloudflare_api_token must be supplied through the SecretSpec terraform scope."
  }
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID"
  type        = string
  sensitive   = false
  nullable    = false
  validation {
    condition     = length(var.cloudflare_zone_id) > 0
    error_message = "cloudflare_zone_id must be supplied through the SecretSpec terraform scope."
  }
}

variable "tailscale_client_id" {
  description = "Tailscale OAuth client ID"
  type        = string
  sensitive   = true
  nullable    = false
  validation {
    condition     = length(var.tailscale_client_id) > 0
    error_message = "tailscale_client_id must be supplied through the SecretSpec terraform scope."
  }
}

variable "tailscale_client_secret" {
  description = "Tailscale OAuth client secret"
  type        = string
  sensitive   = true
  nullable    = false
  validation {
    condition     = length(var.tailscale_client_secret) > 0
    error_message = "tailscale_client_secret must be supplied through the SecretSpec terraform scope."
  }
}
