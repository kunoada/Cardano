# Cardano

## update_trusted_peers
Set the configuration inside the script, to your needs!
AND remember to get the list.peers.yaml too, which includes all known peers

I would recommend to use this script as a sted when restarting your jormungandr node.

As an example from a restart script if jormungandr has failed and need a restart:

systemctl stop jormungandr.service
<RUN update_trusted_peers>
systemctl start jormungandr.service
  
The time it takes to run this script in worst case (If no peers are responding) would be 
timeout*retry*delay*n_peers

As default there will only be one try, and zero delay, and a timeout of three.
In this case it would therefore be;
timeout*n_peers

Any feedback and suggestions are welcome, or if other peers are known which is not in the list.
