import errno
import socket
import time
import commentjson
import yaml

### CONFIGURATIONS ###
retry = 1
delay = 0
timeout = 3
config_path = 'stakepool-config.yaml'
peers_path = 'list_peers.yaml'


def isOpen(ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, int(port)))
        s.shutdown(socket.SHUT_RDWR)
        return True
    except:
        return False
    finally:
        s.close()


def checkHost(ip, port):
    ipup = False
    for i in range(retry):
        if isOpen(ip, port):
                ipup = True
                break
        else:
                time.sleep(delay)
    return ipup


# Read yaml file with the complete list of trusted peers
with open(peers_path, 'r') as stream:
    try:
        trusted_peers = yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        print(exc)

# Read current stakepool configuration file
with open(config_path, 'r') as data_file:
    data = commentjson.load(data_file)

# Delete everything in 'trusted_peers'
del data['p2p']['trusted_peers'][0 : len(data['p2p']['trusted_peers'])]

# Go thru all trusted_peers and add the ones that respond
for trusted_peer in trusted_peers:
    content_split = trusted_peer['address'].split('/')
    if checkHost(content_split[2], content_split[4]):
        print(content_split[2] + " is UP")
        data['p2p']['trusted_peers'].append(
            {
                "address": "{}".format(trusted_peer['address']),
                "id": "{}".format(trusted_peer['id'])
            }
        )
    else:
        print(content_split[2] + " is DOWN")

# Overwrite current stakepool config with the new update list of trusted peers
with open(config_path, 'w') as data_file:
    data = commentjson.dump(data, data_file)