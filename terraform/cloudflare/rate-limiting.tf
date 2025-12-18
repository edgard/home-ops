# Rate limiting for authentication endpoints
# Protects against brute force attacks on Authelia authentication
resource "cloudflare_ruleset" "rate_limit_auth" {
  zone_id     = var.zone_id
  name        = "Rate Limit - Authentication"
  description = "Rate limit for Authelia endpoints"
  kind        = "zone"
  phase       = "http_ratelimit"

  rules = [
    {
      action      = "block"
      expression  = "(http.host eq \"auth.edgard.org\")"
      description = "Rate limit Authelia (auth.edgard.org) - 5 req/10sec, 10sec timeout"
      enabled     = true

      action_parameters = {
        response = {
          status_code  = 429
          content      = "Too many requests. Please try again later."
          content_type = "text/plain"
        }
      }

      ratelimit = {
        characteristics = [
          "cf.colo.id",
          "ip.src"
        ]
        period              = 10
        requests_per_period = 5
        mitigation_timeout  = 10
      }
    }
  ]
}
