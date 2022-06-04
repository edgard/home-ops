# home local hosts
resource "dns_a_record_set" "home_a_records" {
  for_each  = nonsensitive({ for x in yamldecode(data.sops_file.terraform_secrets.raw).local_hosts : x.name => x })
  zone      = "${data.sops_file.terraform_secrets.data["private_domain"]}."
  name      = each.key
  addresses = [each.value.ip]
  ttl       = 300
}

resource "dns_ptr_record" "home_ptr_records" {
  for_each = nonsensitive({ for x in yamldecode(data.sops_file.terraform_secrets.raw).local_hosts : x.name => x })
  zone     = format("%s.in-addr.arpa.", join(".", reverse(slice(split(".", data.sops_file.terraform_secrets.data["lan_cidr"]), 0, 3))))
  name     = trimprefix(each.value.ip, format("%s.", join(".", slice(split(".", data.sops_file.terraform_secrets.data["lan_cidr"]), 0, 3))))
  ptr      = format("%s.%s", each.key, "${data.sops_file.terraform_secrets.data["private_domain"]}.")
  ttl      = 300
}

resource "remote_file" "dhcpd_conf" {
  content = templatefile("home_dhcp.tftpl", { local_hosts = yamldecode(data.sops_file.terraform_secrets.raw).local_hosts })
  path    = "/etc/dhcp/fixed_hosts.conf"

  provisioner "remote-exec" {
    inline = [
      "systemctl restart isc-dhcp-server",
    ]

    connection {
      type        = "ssh"
      host        = data.sops_file.terraform_secrets.data["dns_server_ip"]
      user        = "root"
      private_key = data.sops_file.terraform_secrets.data["ssh_private_key"]
    }
  }
}
