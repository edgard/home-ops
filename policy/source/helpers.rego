package main

import rego.v1

list_contains(keys, key) if {
  some i
  keys[i] == key
}

order_position(keys, key) := pos if {
  some i
  keys[i] == key
  pos := i
}

order_position(keys, key) := 999 if {
  not list_contains(keys, key)
}

ordered_if_present(keys, first, second) if {
  not list_contains(keys, first)
}

ordered_if_present(keys, first, second) if {
  not list_contains(keys, second)
}

ordered_if_present(keys, first, second) if {
  list_contains(keys, first)
  list_contains(keys, second)
  order_position(keys, first) <= order_position(keys, second)
}
