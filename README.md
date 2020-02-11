# Cardano stakepool helpers

## jormungandr_controller
The jormungandr controller is built to automate processes, to ensure an always healthy node is up and running and to ensure maximum uptime while still fully in sync.

## update_trusted_peers
This script pings all trusted peers and rewrite the stakepool-config file with a fully up-to-date trusted peers list.
