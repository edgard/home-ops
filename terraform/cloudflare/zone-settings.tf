# Cloudflare zone settings for edgard.org
# All settings imported to track current configuration

# ============================================================================
# SSL/TLS Settings
# ============================================================================

# SSL Mode (Full Strict)
resource "cloudflare_zone_setting" "ssl" {
  zone_id    = var.zone_id
  setting_id = "ssl"
  value      = "strict"
}

# Always Use HTTPS
resource "cloudflare_zone_setting" "always_use_https" {
  zone_id    = var.zone_id
  setting_id = "always_use_https"
  value      = "on"
}

# Minimum TLS Version
resource "cloudflare_zone_setting" "min_tls_version" {
  zone_id    = var.zone_id
  setting_id = "min_tls_version"
  value      = "1.3"
}

# TLS 1.3 (with 0-RTT)
resource "cloudflare_zone_setting" "tls_1_3" {
  zone_id    = var.zone_id
  setting_id = "tls_1_3"
  value      = "zrt"
}

# 0-RTT (Zero Round Trip Time Resumption)
resource "cloudflare_zone_setting" "zero_rtt" {
  zone_id    = var.zone_id
  setting_id = "0rtt"
  value      = "on"
}

# Automatic HTTPS Rewrites
resource "cloudflare_zone_setting" "automatic_https_rewrites" {
  zone_id    = var.zone_id
  setting_id = "automatic_https_rewrites"
  value      = "on"
}

# ============================================================================
# Security Settings
# ============================================================================

# Security Level
resource "cloudflare_zone_setting" "security_level" {
  zone_id    = var.zone_id
  setting_id = "security_level"
  value      = "medium"
}

# Browser Integrity Check
resource "cloudflare_zone_setting" "browser_check" {
  zone_id    = var.zone_id
  setting_id = "browser_check"
  value      = "on"
}

# Encrypted Client Hello (ECH)
resource "cloudflare_zone_setting" "ech" {
  zone_id    = var.zone_id
  setting_id = "ech"
  value      = "on"
}

# Post-Quantum Key Exchange
resource "cloudflare_zone_setting" "pq_keyex" {
  zone_id    = var.zone_id
  setting_id = "pq_keyex"
  value      = "on"
}

# Privacy Pass
resource "cloudflare_zone_setting" "privacy_pass" {
  zone_id    = var.zone_id
  setting_id = "privacy_pass"
  value      = "on"
}

# Challenge TTL
resource "cloudflare_zone_setting" "challenge_ttl" {
  zone_id    = var.zone_id
  setting_id = "challenge_ttl"
  value      = 1800
}

# ============================================================================
# Performance & Optimization
# ============================================================================

# HTTP/3 (QUIC)
resource "cloudflare_zone_setting" "http3" {
  zone_id    = var.zone_id
  setting_id = "http3"
  value      = "off"
}

# Brotli Compression
resource "cloudflare_zone_setting" "brotli" {
  zone_id    = var.zone_id
  setting_id = "brotli"
  value      = "on"
}

# Opportunistic Encryption
resource "cloudflare_zone_setting" "opportunistic_encryption" {
  zone_id    = var.zone_id
  setting_id = "opportunistic_encryption"
  value      = "on"
}

# Rocket Loader (JS optimization)
resource "cloudflare_zone_setting" "rocket_loader" {
  zone_id    = var.zone_id
  setting_id = "rocket_loader"
  value      = "off"
}

# Early Hints
resource "cloudflare_zone_setting" "early_hints" {
  zone_id    = var.zone_id
  setting_id = "early_hints"
  value      = "on"
}

# Email Obfuscation
resource "cloudflare_zone_setting" "email_obfuscation" {
  zone_id    = var.zone_id
  setting_id = "email_obfuscation"
  value      = "on"
}

# ============================================================================
# Caching Settings
# ============================================================================

# Cache Level
resource "cloudflare_zone_setting" "cache_level" {
  zone_id    = var.zone_id
  setting_id = "cache_level"
  value      = "aggressive"
}

# Browser Cache TTL
resource "cloudflare_zone_setting" "browser_cache_ttl" {
  zone_id    = var.zone_id
  setting_id = "browser_cache_ttl"
  value      = 86400  # 24 hours (was 4 hours)
}

# Edge Cache TTL
resource "cloudflare_zone_setting" "edge_cache_ttl" {
  zone_id    = var.zone_id
  setting_id = "edge_cache_ttl"
  value      = 7200
}

# Always Online (cache when origin down)
resource "cloudflare_zone_setting" "always_online" {
  zone_id    = var.zone_id
  setting_id = "always_online"
  value      = "off"
}

# Development Mode (bypass cache)
resource "cloudflare_zone_setting" "development_mode" {
  zone_id    = var.zone_id
  setting_id = "development_mode"
  value      = "off"
}

# ============================================================================
# Network Settings
# ============================================================================

# IPv6
resource "cloudflare_zone_setting" "ipv6" {
  zone_id    = var.zone_id
  setting_id = "ipv6"
  value      = "off"
}

# IP Geolocation Headers
resource "cloudflare_zone_setting" "ip_geolocation" {
  zone_id    = var.zone_id
  setting_id = "ip_geolocation"
  value      = "on"
}

# Websockets
resource "cloudflare_zone_setting" "websockets" {
  zone_id    = var.zone_id
  setting_id = "websockets"
  value      = "on"
}

# CNAME Flattening
resource "cloudflare_zone_setting" "cname_flattening" {
  zone_id    = var.zone_id
  setting_id = "cname_flattening"
  value      = "flatten_at_root"
}

# ============================================================================
# DNSSEC
# ============================================================================

resource "cloudflare_zone_dnssec" "edgard_org" {
  zone_id = var.zone_id
}
