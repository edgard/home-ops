# DNSEndpoint resources for Unifi DNS (internal split-DNS)
# These mirror the Cloudflare records but target internal Unifi DNS via external-dns

resource "kubernetes_manifest" "github_pages_root" {
  manifest = {
    apiVersion = "externaldns.k8s.io/v1alpha1"
    kind       = "DNSEndpoint"
    metadata = {
      name      = "github-pages-root"
      namespace = "platform-system"
    }
    spec = {
      endpoints = [
        {
          dnsName    = "edgard.org"
          recordTTL  = 1
          recordType = "A"
          targets = [
            "185.199.108.153",
            "185.199.109.153",
            "185.199.110.153",
            "185.199.111.153",
          ]
        }
      ]
    }
  }
}

resource "kubernetes_manifest" "github_pages_www" {
  manifest = {
    apiVersion = "externaldns.k8s.io/v1alpha1"
    kind       = "DNSEndpoint"
    metadata = {
      name      = "github-pages-www"
      namespace = "platform-system"
    }
    spec = {
      endpoints = [
        {
          dnsName    = "www.edgard.org"
          recordTTL  = 1
          recordType = "CNAME"
          targets = [
            "edgard.github.io"
          ]
        }
      ]
    }
  }
}
