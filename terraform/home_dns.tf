# home local hosts
resource "dns_a_record_set" "home_a_records" {
  for_each  = nonsensitive({ for x in yamldecode(data.sops_file.terraform_secrets.raw).local_hosts : x.name => x })
  zone      = "${data.sops_file.terraform_secrets.data["private_domain"]}."
  name      = each.key
  addresses = [each.value.ip]
  ttl       = 300
}

resource "dns_ptr_record" "home_ptr_records" {
  for_each = nonsensitive({ for x in yamldecode(data.sops_file.terraform_secrets.raw).local_hosts : x.name => x if x.ptr == true })
  zone     = format("%s.in-addr.arpa.", join(".", reverse(split(".", data.sops_file.terraform_secrets.data["lan_prefix"]))))
  name     = trimprefix(each.value.ip, format("%s.", data.sops_file.terraform_secrets.data["lan_prefix"]))
  ptr      = format("%s.%s", each.key, "${data.sops_file.terraform_secrets.data["private_domain"]}.")
  ttl      = 300
}

resource "remote_file" "dhcpd_conf" {
  content = templatefile("home_dhcp.tftpl", { local_hosts = yamldecode(data.sops_file.terraform_secrets.raw).local_hosts })
  path    = "/etc/dhcp/fixed_hosts.conf"
}

resource "null_resource" "restart_dhcp_on_change" {
  triggers = {
    file_changed = md5(remote_file.dhcpd_conf.content)
  }

  provisioner "remote-exec" {
    inline = [
      "sudo -S systemctl restart isc-dhcp-server",
    ]
    connection {
      type        = "ssh"
      host        = data.sops_file.terraform_secrets.data["dns_server_ip"]
      user        = "pi"
      private_key = data.sops_file.terraform_secrets.data["ssh_private_key"]
    }
  }
}
