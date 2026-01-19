variable "bw_secret_ids" {
  description = "Map of Bitwarden Secret IDs (UUIDs)"
  type        = map(string)
}

variable "bitwarden_org_id" {
  description = "Bitwarden Organization ID (UUID)"
  type        = string
}
