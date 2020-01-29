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
config = json.load(open('my_config.json' , 'r'))

#### Configuration ####
jcli_call_format = config['Configuration']['jcli_call_format']
jormungandr_call_format = config['Configuration']['jormungandr_call_format']
stakepool_config_path = config['Configuration']['stakepool_config_path']
node_secret_path = config['Configuration']['node_secret_path']
genesis_hash = config['Configuration']['genesis_hash']
number_of_nodes = config['Configuration']['number_of_nodes']
# Pooltool sendmytip setup #
url = config['PooltoolSetup']['url']
pool_id = config['PooltoolSetup']['pool_id']
user_id = config['PooltoolSetup']['user_id']
# All intervals are in seconds
LEADER_ELECTION_INTERVAL = config['Intervals']['LEADER_ELECTION']
TABLE_UPDATE_INTERVAL = config['Intervals']['TABLE_UPDATE']
UPDATE_NODES_INTERVAL = config['Intervals']['UPDATE_NODES']
STUCK_CHECK_INTERVAL = config['Intervals']['STUCK_CHECK']
LAST_SYNC_RESTART = config['Intervals']['LAST_SYNC_RESTART']
SEND_MY_TIP_INTERVAL = config['Intervals']['SEND_MY_TIP']
TRANSITION_CHECK_INTERVAL = config['Intervals']['TRANSITION_CHECK']
#######################

# _________________________________________________________________________________________________________________#

# !DON'T TOUCH THESE VARIABLES! #
stakepool_config = yaml.safe_load(open(stakepool_config_path , 'r'))
tmp_config_file_path = 'tmp.config'
current_leader = -1
pooltoolmax = 0
nodes = {}


def node_init(node_number):
    global nodes
    nodes[f'node_{node_number}'] = {}
    # Start a jormungandr process
    nodes[f'node_{node_number}']['process_id'] = subprocess.Popen(
        [jormungandr_call_format , '--genesis-block-hash' , genesis_hash , '--config' , tmp_config_file_path] ,
        stdout=subprocess.DEVNULL , stderr=subprocess.STDOUT)  # TODO: node should start as leader??? maybe..
    # Give a timestamp when process is born
    nodes[f'node_{node_number}']['timeSinceLastBlock'] = int(time.time())
    nodes[f'node_{node_number}']['lastBlockHeight'] = 0
    nodes[f'node_{node_number}']['lastKnownBlockHeightStuckCheck'] = 0
    nodes[f'node_{node_number}']['lastBlockHash'] = 0
    nodes[f'node_{node_number}']['uptime'] = 0
    nodes[f'node_{node_number}']['state'] = ''


def start_node(node_number):
    # Use a temp copy of stakepool_config
    stakepool_config_temp = copy.deepcopy(stakepool_config)

    # Create a temporarily file, as jormungandr require this as input
    with open(tmp_config_file_path , 'w') as tmp_config_file:
        # Increase port number for specific node
        ip_address , port = stakepool_config_temp['rest']['listen'].split(':')
        stakepool_config_temp['rest']['listen'] = ip_address + ':' + str(int(port) + node_number)
        # Listen_address
        x , ip , ip_address , comm_p , port = stakepool_config_temp['p2p']['listen_address'].split('/')
        stakepool_config_temp['p2p']['listen_address'] = f'/{ip}/{ip_address}/{comm_p}/{int(port) + node_number}'
        # Public_address
        x , ip , ip_address , comm_p , port = stakepool_config_temp['p2p']['public_address'].split('/')
        stakepool_config_temp['p2p']['public_address'] = f'/{ip}/{ip_address}/{comm_p}/{int(port) + node_number}'
        # Save in temp config file
        json.dump(stakepool_config_temp , tmp_config_file)

    node_init(node_number)
    print(f'Starting node {node_number}...')

    time.sleep(5)
    os.remove(tmp_config_file_path)


def start_nodes():
    # Start (number_of_nodes) new nodes
    for i in range(number_of_nodes):
        start_node(i)


def update_nodes_info():
    threading.Timer(UPDATE_NODES_INTERVAL , update_nodes_info).start()

    global nodes
    ip_address , port = stakepool_config['rest']['listen'].split(':')

    for i in range(number_of_nodes):
        try:
            node_stats = yaml.safe_load(subprocess.check_output(
                [jcli_call_format , 'rest' , 'v0' , 'node' , 'stats' , 'get' , '-h' ,
                 f'http://{ip_address}:{int(port) + i}/api']).decode(
                'utf-8'))

            if node_stats['state'] == 'Running':
                if nodes[f'node_{i}']['lastBlockHeight'] < int(node_stats['lastBlockHeight']):
                    nodes[f'node_{i}']['lastBlockHeight'] = int(node_stats['lastBlockHeight'])
                    nodes[f'node_{i}']['timeSinceLastBlock'] = int(time.time())
                nodes[f'node_{i}']['lastBlockHash'] = node_stats['lastBlockHash']
                nodes[f'node_{i}']['state'] = 'Running'
                nodes[f'node_{i}']['uptime'] = node_stats['uptime']

            elif node_stats['state'] == 'Bootstrapping':
                nodes[f'node_{i}']['lastBlockHeight'] = 0
                nodes[f'node_{i}']['lastBlockHash'] = ''
                nodes[f'node_{i}']['state'] = 'Bootstrapping'

        except subprocess.CalledProcessError as e:
            nodes[f'node_{i}']['lastBlockHeight'] = 0
            nodes[f'node_{i}']['lastBlockHash'] = ''
            nodes[f'node_{i}']['state'] = 'Starting'
            continue


# ./jcli rest v0 leaders logs get -h http://127.0.0.1:3100/api
# ./jcli rest v0 node stats get -h http://127.0.0.1:3100/api
def leader_election():
    threading.Timer(LEADER_ELECTION_INTERVAL , leader_election).start()

    global current_leader
    ip_address , port = stakepool_config['rest']['listen'].split(':')

    healthiest_node = -1
    highest_blockheight = 0

    # Find healthiest node, (highest node)
    for i in range(number_of_nodes):

        if highest_blockheight < nodes[f'node_{i}']['lastBlockHeight']:
            highest_blockheight = nodes[f'node_{i}']['lastBlockHeight']
            healthiest_node = i

    if healthiest_node < 0:
        return

    if current_leader != healthiest_node:
        print(f'Changing leader from {current_leader} to {healthiest_node}')
        # Select leader
        subprocess.run([jcli_call_format , 'rest' , 'v0' , 'leaders' , 'post' , '-f' , node_secret_path , '-h' ,
                        f'http://{ip_address}:{int(port) + healthiest_node}/api'])
        if not current_leader < 0:
            # Delete old leader
            subprocess.run([jcli_call_format , 'rest' , 'v0' , 'leaders' , 'delete' , '1' , '-h' ,
                            f'http://{ip_address}:{int(port) + current_leader}/api'])
        # Update current leader
        current_leader = healthiest_node


def is_nodes_running():
    ip_address , port = stakepool_config['rest']['listen'].split(':')

    for i in range(number_of_nodes):
        try:
            output = yaml.safe_load(subprocess.check_output(
                [jcli_call_format , 'rest' , 'v0' , 'node' , 'stats' , 'get' , '-h' ,
                 f'http://{ip_address}:{int(port) + i}/api']).decode('utf-8'))
            if output['state'] == 'Bootstrapping':
                return i
        except subprocess.CalledProcessError as e:
            pass

    return -1


def stuck_check():
    threading.Timer(STUCK_CHECK_INTERVAL , stuck_check).start()

    global nodes

    for i in range(number_of_nodes):

        if int(time.time()) - nodes[f'node_{i}']['timeSinceLastBlock'] > LAST_SYNC_RESTART:
            print(f'Node {i} is restarting due to out of sync or stuck in bootstrapping')
            # Kill process
            nodes[f'node_{i}']['process_id'].kill()
            # Give it some time to shutdown
            time.sleep(5)
            # Start a jormungandr process
            start_node(i)


def table_update():
    threading.Timer(TABLE_UPDATE_INTERVAL , table_update).start()

    headers = ['Node' , 'State' , 'Block height' , 'pooltoolmax' , 'Delta' , 'Uptime' , 'Time since last sync' ,
               'Current leader']
    data = []

    for i in range(number_of_nodes):
        temp_list = []
        temp_list.extend(
            [f'Node {i}' , nodes[f'node_{i}']['state'] , nodes[f'node_{i}']['lastBlockHeight'] , pooltoolmax ,
             nodes[f'node_{i}']['lastBlockHeight'] - pooltoolmax , nodes[f'node_{i}']['uptime'] ,
             int(time.time()) - nodes[f'node_{i}']['timeSinceLastBlock']])

        if i == current_leader:
            temp_list.append(1)
        else:
            temp_list.append(0)

        data.append(temp_list)

    # clear()
    print(tabulate(data , headers))


def send_my_tip():
    threading.Timer(SEND_MY_TIP_INTERVAL , send_my_tip).start()

    global pooltoolmax

    if not current_leader < 0:
        # lastPoolID =$(cli block ${lastBlockHash} get | cut -c169-232)
        ip_address , port = stakepool_config['rest']['listen'].split(':')
        try:
            stats = yaml.safe_load(subprocess.check_output(
                [jcli_call_format , 'rest' , 'v0' , 'block' , nodes[f'node_{current_leader}']['lastBlockHash'] , 'get' ,
                 '-h' ,
                 f'http://{ip_address}:{int(port) + current_leader}/api']).decode(
                'utf-8'))
            # test = subprocess.check_output([f'echo "{stats}"', '|', 'cut -c169-232'], shell=True)
            PARAMS = {'poolid': pool_id , 'userid': user_id , 'genesispref': genesis_hash ,
                      'mytip': nodes[f'node_{current_leader}']['lastBlockHeight'] ,
                      'lasthash': nodes[f'node_{current_leader}']['lastBlockHash'] , 'lastpool': stats}
            # sending get request and saving the response as response object
            r = requests.get(url=url , params=PARAMS)

            # extracting data in json format
            data = r.json()
            if data['success']:
                pooltoolmax = int(data['pooltoolmax'])

        except subprocess.CalledProcessError as e:
            pass


# This method is based on
# https://github.com/rdlrt/Alternate-Jormungandr-Testnet/blob/master/scripts/jormungandr-leaders-failover.sh
def check_transition():
    threading.Timer(TRANSITION_CHECK_INTERVAL , check_transition).start()

    ip_address , port = stakepool_config['rest']['listen'].split(':')
    settings = yaml.safe_load(subprocess.check_output(
        [jcli_call_format , 'rest' , 'v0' , 'settings' , 'get' , '-h' , f'http://{ip_address}:{int(port)}/api']))
    slot_duration = int(settings['slotDuration'])
    slots_per_epoch = int(settings['slotsPerEpoch'])

    curr_slot = (
                (((int(time.time()) - 1576264417) / slot_duration) % (slots_per_epoch * slot_duration)) / slot_duration)
    diff_epoch_end = slots_per_epoch - curr_slot

    if diff_epoch_end < slot_duration + 5:  # Adds a small probability of creating an adversarial fork if assigned for last 3 slots of the epoch, or first 3 slots of next epoch
        print("Adding keys to all nodes for epoch transition:")

        for i in range(number_of_nodes):
            subprocess.run([jcli_call_format , 'rest' , 'v0' , 'leaders' , 'post' , '-f' , node_secret_path , '-h' ,
                            f'http://{ip_address}:{int(port) + i}/api'])

        # Wait until new epoch
        time.sleep(slot_duration + 10)

        for i in range(number_of_nodes):
            # Delete leaders except one
            if not i == current_leader:
                subprocess.run([jcli_call_format , 'rest' , 'v0' , 'leaders' , 'delete' , '1' , '-h' ,
                                f'http://{ip_address}:{int(port) + i}/api'])


def clear():
    # check and make call for specific operating system
    _ = subprocess.call(['clear' if os.name == 'posix' else 'cls'])


def main():
    # nodes_running = -1

    start_nodes()
    # Wait until at least one node is up and running #TODO: Is this really needed?
    # while 0 > nodes_running:
    #     time.sleep(60)
    #     nodes_running = is_nodes_running()

    update_nodes_info()
    leader_election()
    table_update()
    stuck_check()
    send_my_tip()


if __name__ == "__main__":
    main()
