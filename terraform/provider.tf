terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = ">= 3.16.0"
    }
    dns = {
      source  = "hashicorp/dns"
      version = ">= 3.2.3"
    }
    remote = {
      source  = "tenstad/remote"
      version = ">= 0.1.0"
    }
    sops = {
      source  = "carlpett/sops"
      version = ">= 0.7.1"
    }
  }
  required_version = ">= 1.1.9"
}

data "sops_file" "terraform_secrets" {
  source_file = "secrets.sops.yaml"
}

provider "cloudflare" {
  email   = data.sops_file.terraform_secrets.data["email"]
  api_key = data.sops_file.terraform_secrets.data["cloudflare_api_key"]
}

provider "dns" {
  update {
    server        = data.sops_file.terraform_secrets.data["dns_server_ip"]
    key_name      = "rndc-key."
    key_algorithm = "hmac-sha256"
    key_secret    = data.sops_file.terraform_secrets.data["dns_key_secret"]
  }
}

provider "remote" {
  conn {
    host        = data.sops_file.terraform_secrets.data["dns_server_ip"]
    user        = "root"
    private_key = data.sops_file.terraform_secrets.data["ssh_private_key"]
  }
}
