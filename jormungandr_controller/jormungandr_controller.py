import subprocess
import threading
from tabulate import tabulate
import copy
import time
import json
import yaml
import os

# TODO: Put configuration in a config file
#### Configuration ####
jcli_call_format        = '../jcli'
jormungandr_call_format = '../jormungandr'
stakepool_config_path   = '../test_documents/stakepool-config.yaml'
genesis_hash_path       = '../test_documents/genesis-hash.txt'
node_secret_path        = '../test_documents/node-secret.yaml'
number_of_nodes         = 3
# All intervals are in seconds
LEADER_ELECTION_INTERVAL = 60
STATS_UPDATE_INTERVAL = 5
#######################

tmp_config_file_path    = 'tmp.config'  # Just use default (this file will be deleted again anyway)
stakepool_config = json.load(open(stakepool_config_path, 'r'))
nodes = {}
current_leader = -1


def start_nodes():
    # Use a temp copy of stakepool_config
    stakepool_config_temp = copy.deepcopy(stakepool_config)
    genesis_hash = open(genesis_hash_path, 'r').read()

    # Start (number_of_nodes) new nodes
    for i in range(number_of_nodes):

        # Create a temporarily file, as jormungandr require this as input
        with open(tmp_config_file_path, 'w') as tmp_config_file:
            json.dump(stakepool_config_temp, tmp_config_file)

        # Start a jormungandr process
        nodes[f'process_{i}'] = subprocess.Popen(
            [jormungandr_call_format, '--genesis-block-hash', genesis_hash, '--config', tmp_config_file_path], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT) # TODO: one node need to be leader??? maybe..

        # Increase port number for next node
        # Rest
        ip_address, port = stakepool_config_temp['rest']['listen'].split(':')
        stakepool_config_temp['rest']['listen'] = ip_address + ':' + str(int(port) + 1)
        # Listen_address
        x, ip, ip_address, comm_p, port = stakepool_config_temp['p2p']['listen_address'].split('/')
        stakepool_config_temp['p2p']['listen_address'] = f'/{ip}/{ip_address}/{comm_p}/{str(int(port) + 1)}'
        # Public_address
        x, ip, ip_address, comm_p, port = stakepool_config_temp['p2p']['public_address'].split('/')
        stakepool_config_temp['p2p']['public_address'] = f'/{ip}/{ip_address}/{comm_p}/{str(int(port) + 1)}'

        time.sleep(10)

    # Give jormungandr some time to start before deleting the temp config file
    time.sleep(5)
    os.remove(tmp_config_file_path)


# ./jcli rest v0 leaders logs get -h http://127.0.0.1:3100/api
# ./jcli rest v0 node stats get -h http://127.0.0.1:3100/api
def leader_election():
    global current_leader
    ip_address, port = stakepool_config['rest']['listen'].split(':')

    healthiest_node = -1
    highest_blockheight = 0

    # Find healthiest node, (highest node) #TODO: change to lowest difference to currentBlockHeight
    for i in range(number_of_nodes):
        try:
            node_stats = yaml.safe_load(subprocess.check_output(
                [jcli_call_format, 'rest', 'v0', 'node', 'stats', 'get', '-h', f'http://{ip_address}:{port}/api']).decode(
                'utf-8'))
            if 'lastBlockHeight' in node_stats:
                lastBlockHeight = int(node_stats['lastBlockHeight'])
            elif 'state' in node_stats:
                if node_stats['state'] == 'Bootstrapping':
                    continue
        except subprocess.CalledProcessError as e:
            port = int(port) + 1
            continue

        if isinstance(lastBlockHeight, int):
            if highest_blockheight < lastBlockHeight:
                highest_blockheight = lastBlockHeight
                healthiest_node = i

        port = int(port) + 1

    if healthiest_node < 0:
        return

    if current_leader != healthiest_node:
        # Reset port to default
        port = port - number_of_nodes
        # Select leader
        subprocess.run([jcli_call_format, 'rest', 'v0', 'leaders', 'post', '-f', node_secret_path, '-h', f'http://{ip_address}:{port + healthiest_node}/api'])
        # Delete old leader
        subprocess.run([jcli_call_format, 'rest', 'v0', 'leaders', 'delete', '1', '-h', f'http://{ip_address}:{port + current_leader}/api'])
        # Update current leader
        current_leader = healthiest_node

    threading.Timer(LEADER_ELECTION_INTERVAL, leader_election).start()


def is_nodes_running():

    ip_address, port = stakepool_config['rest']['listen'].split(':')

    for i in range(number_of_nodes):
        try:
            output = yaml.safe_load(subprocess.check_output(
                [jcli_call_format, 'rest', 'v0', 'node', 'stats', 'get', '-h', f'http://{ip_address}:{port}/api']).decode('utf-8'))
            if output['state'] == 'Running':
                return i
        except subprocess.CalledProcessError as e:
            pass

        port = int(port) + 1

    return -1


def stuck_check():
    # TODO: needs to be made
    print("checking")


def stats_update():
    headers = ['Node', 'State', 'Block height', 'Uptime', 'Current leader']
    ip_address, port = stakepool_config['rest']['listen'].split(':')
    data = []

    for i in range(number_of_nodes):
        temp_list = []
        try:
            stats = yaml.safe_load(subprocess.check_output(
                [jcli_call_format, 'rest', 'v0', 'node', 'stats', 'get', '-h', f'http://{ip_address}:{port}/api']).decode(
                'utf-8'))

            if stats['state'] == 'Running':
                temp_list.extend([f'Node {i}', stats['state'], stats['lastBlockHeight'], stats['uptime']])
            elif stats['state'] == 'Bootstrapping':
                temp_list.extend([f'Node {i}', stats['state'], '?', '?'])

            if i == current_leader:
                temp_list.append(1)
            else:
                temp_list.append(0)

        except subprocess.CalledProcessError as e:
            pass

        port = int(port) + 1
        data.append(temp_list)

    # clear()
    print(tabulate(data, headers))
    threading.Timer(STATS_UPDATE_INTERVAL, stats_update).start()


def clear():
    # check and make call for specific operating system
    _ = subprocess.call(['clear' if os.name == 'posix' else 'cls'])


def main():
    nodes_running = -1

    start_nodes()
    # Wait until at least one node is up and running
    while 0 > nodes_running:
        nodes_running = is_nodes_running()
        time.sleep(60)

    leader_election()
    stats_update()


if __name__ == "__main__":
    main()

# def check_transition():
#     # FROM : https://github.com/rdlrt/Alternate-Jormungandr-Testnet/blob/master/scripts/jormungandr-leaders-failover.sh
#     ip_address, port = stakepool_config['rest']['listen'].split(':')
#     settings = yaml.safe_load(subprocess.check_output([jcli_call_format, 'rest', 'v0', 'settings', 'get', '-h', f'http://{ip_address}:{int(port)}/api']))
#     slotDuration = int(settings['slotDuration'])  #  $(jcli rest v0 settings get --output-format json -h $J1_URL | jq -r .slotDuration)
#     slotsPerEpoch = int(settings['slotsPerEpoch'])  #  $(jcli rest v0 settings get --output-format json -h $J1_URL | jq -r .slotsPerEpoch)
#
#     currslot = ((((int(time.time()) - 1576264417) / slotDuration) % (slotsPerEpoch * slotDuration)) / slotDuration) #  $((((($(date +%s)-1576264417)/$slotDuration)%($slotsPerEpoch*$slotDuration))/$slotDuration))

  # diffepochend=$(expr $slotsPerEpoch - $currslot)
  # hdiff=$(( $lBH2 - $lBH1 ))
  # if [ $diffepochend -lt $(($slotDuration+1)) ]; then # Adds a small probability of losing very rare leadership task if assigned for last slot of the epoch, or first block of next epoch
  #   echo "Adding keys to both nodes for epoch transition:"
  #   # Based on this script J1 is active and will always have the leader key, so add to J2
  #   jcli rest v0 leaders post -f $jkey -h $J2_URL
  #   sleep $(($slotDuration+1))
  #   jcli rest v0 leaders delete 1 -h $J2_URL
  # fi
