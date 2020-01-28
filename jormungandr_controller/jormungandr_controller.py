import subprocess
import threading
import requests
from tabulate import tabulate
import copy
import time
import json
import yaml
import os

# TODO: Put configuration in a config file
#### Configuration ####
jcli_call_format = '../jcli'
jormungandr_call_format = '../jormungandr'
stakepool_config_path = '../test_documents/stakepool-config.yaml'
genesis_hash_path = '../test_documents/genesis-hash.txt'
node_secret_path = '../test_documents/node-secret.yaml'
number_of_nodes = 3
# Pooltool sendmytip setup #
URL = "https://api.pooltool.io/v0/sharemytip"
pool_id = '778f18a9c3a9b8dc03146ee9d71afc577bb63fd2f9'
user_id = ''
# All intervals are in seconds
LEADER_ELECTION_INTERVAL = 60
STATS_UPDATE_INTERVAL = 10
STUCK_CHECK_INTERVAL = 30
LAST_SYNC_RESTART = 300
SEND_MY_TIP_INTERVAL = 30
#######################

# _________________________________________________________________________________________________________________#

# !DON'T TOUCH THESE VARIABLES! #
genesis_hash = open(genesis_hash_path, 'r').read().replace('\n', '')  # Replace needed in order to work on linux...
stakepool_config = json.load(open(stakepool_config_path, 'r'))
tmp_config_file_path = 'tmp.config'
current_leader = -1
nodes = {}


def start_node(node_number):
    # Use a temp copy of stakepool_config
    stakepool_config_temp = copy.deepcopy(stakepool_config)

    # Create a temporarily file, as jormungandr require this as input
    with open(tmp_config_file_path, 'w') as tmp_config_file:
        # Increase port number for specific node
        ip_address, port = stakepool_config_temp['rest']['listen'].split(':')
        stakepool_config_temp['rest']['listen'] = ip_address + ':' + str(int(port) + node_number)
        # Listen_address
        x, ip, ip_address, comm_p, port = stakepool_config_temp['p2p']['listen_address'].split('/')
        stakepool_config_temp['p2p']['listen_address'] = f'/{ip}/{ip_address}/{comm_p}/{int(port) + node_number}'
        # Public_address
        x, ip, ip_address, comm_p, port = stakepool_config_temp['p2p']['public_address'].split('/')
        stakepool_config_temp['p2p']['public_address'] = f'/{ip}/{ip_address}/{comm_p}/{int(port) + node_number}'
        # Save in temp config file
        json.dump(stakepool_config_temp, tmp_config_file)

    nodes[f'node_{node_number}'] = {}
    # Start a jormungandr process
    nodes[f'node_{node_number}']['process_id'] = subprocess.Popen(
        [jormungandr_call_format, '--genesis-block-hash', genesis_hash, '--config', tmp_config_file_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)  # TODO: node should start as leader??? maybe..
    # Give a timestamp when process is born
    nodes[f'node_{node_number}']['timeSinceLastBlock'] = int(time.time())
    nodes[f'node_{node_number}']['lastBlockHeight'] = 0
    print(f'Starting node {node_number}...')

    time.sleep(10)
    os.remove(tmp_config_file_path)


def start_nodes():
    # Start (number_of_nodes) new nodes
    for i in range(number_of_nodes):
        start_node(i)


# ./jcli rest v0 leaders logs get -h http://127.0.0.1:3100/api
# ./jcli rest v0 node stats get -h http://127.0.0.1:3100/api
def leader_election():
    global current_leader
    ip_address, port = stakepool_config['rest']['listen'].split(':')

    healthiest_node = -1
    highest_blockheight = 0

    # Find healthiest node, (highest node)
    for i in range(number_of_nodes):
        try:
            node_stats = yaml.safe_load(subprocess.check_output(
                [jcli_call_format, 'rest', 'v0', 'node', 'stats', 'get', '-h',
                 f'http://{ip_address}:{port}/api']).decode(
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
        print(f'Changing leader from {current_leader} to {healthiest_node}')
        # Reset port to default
        port = port - number_of_nodes
        # Select leader
        subprocess.run([jcli_call_format, 'rest', 'v0', 'leaders', 'post', '-f', node_secret_path, '-h',
                        f'http://{ip_address}:{port + healthiest_node}/api'])
        # Delete old leader
        subprocess.run([jcli_call_format, 'rest', 'v0', 'leaders', 'delete', '1', '-h',
                        f'http://{ip_address}:{port + current_leader}/api'])
        # Update current leader
        current_leader = healthiest_node

    threading.Timer(LEADER_ELECTION_INTERVAL, leader_election).start()


def is_nodes_running():
    ip_address, port = stakepool_config['rest']['listen'].split(':')

    for i in range(number_of_nodes):
        try:
            output = yaml.safe_load(subprocess.check_output(
                [jcli_call_format, 'rest', 'v0', 'node', 'stats', 'get', '-h',
                 f'http://{ip_address}:{port}/api']).decode('utf-8'))
            if output['state'] == 'Running':
                return i
        except subprocess.CalledProcessError as e:
            pass

        port = int(port) + 1

    return -1


def stuck_check():
    ip_address, port = stakepool_config['rest']['listen'].split(':')

    for i in range(number_of_nodes):
        try:
            stats = yaml.safe_load(subprocess.check_output(
                [jcli_call_format, 'rest', 'v0', 'node', 'stats', 'get', '-h',
                 f'http://{ip_address}:{port}/api']).decode(
                'utf-8'))

            if stats['state'] == 'Running':
                if int(nodes[f'node_{i}']['lastBlockHeight']) < int(stats['lastBlockHeight']):
                    nodes[f'node_{i}']['lastBlockHeight'] = stats['lastBlockHeight']
                    nodes[f'node_{i}']['timeSinceLastBlock'] = int(time.time())
                    nodes[f'node_{i}']['lastBlockHash'] = stats['lastBlockHash']

        except subprocess.CalledProcessError as e:
            pass

        if int(time.time()) - nodes[f'node_{i}']['timeSinceLastBlock'] > LAST_SYNC_RESTART:
            print(f'Node {i} is restarting due to out of sync or stuck in bootstrapping')
            # Kill process
            nodes[f'node_{i}']['process_id'].kill()
            # Give it some time to shutdown
            time.sleep(5)
            # Start a jormungandr process
            start_node(i)

        port = int(port) + 1

    threading.Timer(STUCK_CHECK_INTERVAL, stuck_check).start()


def stats_update():
    headers = ['Node', 'State', 'Block height', 'pooltoolmax', 'Delta', 'Uptime', 'Time since last sync',
               'Current leader']
    ip_address, port = stakepool_config['rest']['listen'].split(':')
    data = []

    for i in range(number_of_nodes):
        temp_list = []
        try:
            stats = yaml.safe_load(subprocess.check_output(
                [jcli_call_format, 'rest', 'v0', 'node', 'stats', 'get', '-h',
                 f'http://{ip_address}:{port}/api']).decode(
                'utf-8'))

            if stats['state'] == 'Running':
                temp_list.extend([f'Node {i}', stats['state'], stats['lastBlockHeight'], pooltoolmax,
                                  int(stats['lastBlockHeight']) - pooltoolmax, stats['uptime'],
                                  int(time.time()) - nodes[f'node_{i}']['timeSinceLastBlock']])
            elif stats['state'] == 'Bootstrapping':
                temp_list.extend([f'Node {i}', stats['state'], '?', '?', '?', '?',
                                  int(time.time()) - nodes[f'node_{i}']['timeSinceLastBlock']])

            if i == current_leader:
                temp_list.append(1)
            else:
                temp_list.append(0)

        except subprocess.CalledProcessError as e:
            temp_list.extend([f'Node {i}', 'Starting', '?', '?', '?', '?', '?', '0'])
            pass

        port = int(port) + 1
        data.append(temp_list)

    # clear()
    print(tabulate(data, headers))
    threading.Timer(STATS_UPDATE_INTERVAL, stats_update).start()


pooltoolmax = 0


def send_my_tip():
    global pooltoolmax
    # lastPoolID =$(cli block ${lastBlockHash} get | cut -c169-232)
    ip_address, port = stakepool_config['rest']['listen'].split(':')
    try:
        stats = yaml.safe_load(subprocess.check_output(
            [jcli_call_format, 'rest', 'v0', 'block', nodes[f'node_{current_leader}']['lastBlockHash'], 'get', '-h',
             f'http://{ip_address}:{int(port) + current_leader}/api']).decode(
            'utf-8'))
        #test = subprocess.check_output([f'echo "{stats}"', '|', 'cut -c169-232'], shell=True)
        PARAMS = {'poolid': pool_id, 'userid': user_id, 'genesispref': genesis_hash,
                  'mytip': nodes[f'node_{current_leader}']['lastBlockHeight'],
                  'lasthash': nodes[f'node_{current_leader}']['lastBlockHash'], 'lastpool': stats}
        # sending get request and saving the response as response object
        r = requests.get(url=URL, params=PARAMS)

        # extracting data in json format
        data = r.json()
        if data['success']:
            pooltoolmax = int(data['pooltoolmax'])

    except subprocess.CalledProcessError as e:
        pass

    threading.Timer(SEND_MY_TIP_INTERVAL, send_my_tip).start()


def clear():
    # check and make call for specific operating system
    _ = subprocess.call(['clear' if os.name == 'posix' else 'cls'])


def main():
    nodes_running = -1

    start_nodes()
    # Wait until at least one node is up and running
    while 0 > nodes_running:
        time.sleep(60)
        nodes_running = is_nodes_running()

    leader_election()
    stats_update()
    stuck_check()
    send_my_tip()


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
