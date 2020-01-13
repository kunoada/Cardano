# Cardano

## update_trusted_peers
Handles both yaml and json format!
### Dependencies needed;
- PyYAML
- commentjson

---------------------

Set the configuration inside the script, to your needs!
AND remember to get the list_peers.yaml too, which includes all known peers

I would recommend to use this script as a step when restarting your jormungandr node.

As an example from a restart script if jormungandr has failed and need a restart:
```
systemctl stop jormungandr.service
\<RUN update_trusted_peers\>
systemctl start jormungandr.service
```
Any feedback and suggestions are welcome, or if other peers are known which is not in the list.
