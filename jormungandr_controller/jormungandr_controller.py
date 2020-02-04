import copy
import datetime
import json
import os
import collections
import subprocess
import threading
import time
import re

import requests
import yaml
from tabulate import tabulate

config = json.load(open('my_config.json', 'r'))

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
LEADERS_CHECK_INTERVAL = config['Intervals']['LEADERS_CHECK']
#######################

# _________________________________________________________________________________________________________________#

# !DON'T TOUCH THESE VARIABLES! #
stakepool_config = yaml.safe_load(open(stakepool_config_path, 'r'))
tmp_config_file_path = 'tmp.config'
current_leader = -1
pooltoolmax = 0
nodes = {}


def node_init(node_number):
    global nodes
    nodes[f'node_{node_number}'] = {}
    # Start a jormungandr process
    nodes[f'node_{node_number}']['process_id'] = subprocess.Popen(
        [jormungandr_call_format, '--genesis-block-hash', genesis_hash, '--config', tmp_config_file_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)  # TODO: node should start as leader??? maybe..
    # Give a timestamp when process is born
    nodes[f'node_{node_number}']['timeSinceLastBlock'] = int(time.time())
    nodes[f'node_{node_number}']['lastBlockHeight'] = 0
    nodes[f'node_{node_number}']['lastBlockHash'] = 0
    nodes[f'node_{node_number}']['lastBlockTime'] = ''
    nodes[f'node_{node_number}']['lastReceivedBlockTime'] = ''
    nodes[f'node_{node_number}']['uptime'] = 0
    nodes[f'node_{node_number}']['state'] = ''
    nodes[f'node_{node_number}']['latency'] = 10000
    nodes[f'node_{node_number}']['last5LatencyRecords'] = collections.deque(maxlen=5)
    nodes[f'node_{node_number}']['avgLatencyRecords'] = 10000
    nodes[f'node_{node_number}']['leadersLogs'] = []
    nodes[f'node_{node_number}']['numberOfConnections'] = 0


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

    node_init(node_number)
    print(f'Starting node {node_number}...')

    time.sleep(5)
    os.remove(tmp_config_file_path)


def start_nodes():
    # Start (number_of_nodes) new nodes
    for i in range(number_of_nodes):
        start_node(i)


def update_nodes_info():
    global nodes
    ip_address, port = stakepool_config['rest']['listen'].split(':')

    for i in range(number_of_nodes):
        try:

            node_stats = yaml.safe_load(subprocess.check_output(
                [jcli_call_format, 'rest', 'v0', 'node', 'stats', 'get', '-h',
                 f'http://{ip_address}:{int(port) + i}/api']).decode(
                'utf-8'))

            if node_stats['state'] == 'Running':
                network_stats = get_network_stats(i)
                if nodes[f'node_{i}']['lastBlockHeight'] < int(node_stats['lastBlockHeight']):
                    nodes[f'node_{i}']['lastBlockHeight'] = int(node_stats['lastBlockHeight'])
                    nodes[f'node_{i}']['timeSinceLastBlock'] = int(time.time())
                    nodes[f'node_{i}']['lastBlockTime'] = node_stats['lastBlockTime']
                    nodes[f'node_{i}']['lastReceivedBlockTime'] = node_stats['lastReceivedBlockTime']
                    if nodes[f'node_{i}']['lastReceivedBlockTime'] is not None and nodes[f'node_{i}'][
                        'lastReceivedBlockTime'] != '':
                        nodes[f'node_{i}']['latency'] = time_between(
                            re.sub(r"([\+-]\d\d):(\d\d)(?::(\d\d(?:.\d+)?))?", r"\1\2\3", node_stats['lastBlockTime']),
                            re.sub(r"([\+-]\d\d):(\d\d)(?::(\d\d(?:.\d+)?))?", r"\1\2\3",
                                   node_stats['lastReceivedBlockTime']))
                        nodes[f'node_{i}']['last5LatencyRecords'].append(nodes[f'node_{i}']['latency'])
                        if len(list(nodes[f'node_{i}']['last5LatencyRecords'])):
                            nodes[f'node_{i}']['avgLatencyRecords'] = sum(
                                list(nodes[f'node_{i}']['last5LatencyRecords'])) / len(
                                list(nodes[f'node_{i}']['last5LatencyRecords']))
                nodes[f'node_{i}']['lastBlockHash'] = node_stats['lastBlockHash']
                nodes[f'node_{i}']['state'] = 'Running'
                nodes[f'node_{i}']['uptime'] = node_stats['uptime']
                nodes[f'node_{i}']['numberOfConnections'] = len(network_stats)

            elif node_stats['state'] == 'Bootstrapping':
                nodes[f'node_{i}']['lastBlockHeight'] = 0
                nodes[f'node_{i}']['lastBlockHash'] = ''
                nodes[f'node_{i}']['state'] = 'Bootstrapping'

        except subprocess.CalledProcessError as e:
            nodes[f'node_{i}']['lastBlockHeight'] = 0
            nodes[f'node_{i}']['lastBlockHash'] = ''
            nodes[f'node_{i}']['state'] = 'Starting'
            continue

    threading.Timer(UPDATE_NODES_INTERVAL, update_nodes_info).start()


# ./jcli rest v0 leaders logs get -h http://127.0.0.1:3100/api
# ./jcli rest v0 node stats get -h http://127.0.0.1:3100/api
def leader_election():
    global current_leader
    ip_address, port = stakepool_config['rest']['listen'].split(':')

    healthiest_node = -1
    highest_blockheight = 0
    lowest_latency = 10000

    # Find healthiest node, (highest node)
    for i in range(number_of_nodes):

        if highest_blockheight < nodes[f'node_{i}']['lastBlockHeight']:
            highest_blockheight = nodes[f'node_{i}']['lastBlockHeight']
            lowest_latency = nodes[f'node_{i}']['avgLatencyRecords']
            healthiest_node = i
            continue
        elif highest_blockheight == nodes[f'node_{i}']['lastBlockHeight'] and lowest_latency > nodes[f'node_{i}']['avgLatencyRecords']:
            lowest_latency = nodes[f'node_{i}']['avgLatencyRecords']
            healthiest_node = i

    # if healthiest_node < 0 or is_in_transition:
    #     return

    if current_leader != healthiest_node and not is_in_transition and healthiest_node >= 0:
        print(f'Changing leader from {current_leader} to {healthiest_node}')

        try:
            # Select leader
            subprocess.run([jcli_call_format, 'rest', 'v0', 'leaders', 'post', '-f', node_secret_path, '-h',
                            f'http://{ip_address}:{int(port) + healthiest_node}/api'])
        except subprocess.CalledProcessError as e:
            print("Could not elect new leader, skipping")
            return

        if not current_leader < 0:
            # Delete old leader
            subprocess.run([jcli_call_format, 'rest', 'v0', 'leaders', 'delete', '1', '-h',
                            f'http://{ip_address}:{int(port) + current_leader}/api'])
        # Update current leader
        current_leader = healthiest_node

    threading.Timer(LEADER_ELECTION_INTERVAL, leader_election).start()


def stuck_check():
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

    threading.Timer(STUCK_CHECK_INTERVAL, stuck_check).start()


def time_between(d1, d2):
    d1 = datetime.datetime.strptime(d1, "%Y-%m-%dT%H:%M:%S%z")
    d2 = datetime.datetime.strptime(d2, "%Y-%m-%dT%H:%M:%S%z")
    return abs((d2 - d1).seconds)


def table_update():
    threading.Timer(TABLE_UPDATE_INTERVAL, table_update).start()

    headers = ['Node', 'State', 'Block height', 'pooltoolmax', 'Delta', 'Uptime', 'Time since last sync',
               'Current leader']
    data = []

    for i in range(number_of_nodes):
        temp_list = []
        temp_list.extend(
            [f'Node {i}', nodes[f'node_{i}']['state'], nodes[f'node_{i}']['lastBlockHeight'], pooltoolmax,
             nodes[f'node_{i}']['lastBlockHeight'] - pooltoolmax, nodes[f'node_{i}']['uptime'],
             int(time.time()) - nodes[f'node_{i}']['timeSinceLastBlock']])

        if i == current_leader or is_in_transition:
            temp_list.append(1)
        else:
            temp_list.append(0)

        data.append(temp_list)

    # clear()
    print(tabulate(data, headers))
    print('')

    headers = ['Node', 'lastBlockTime', 'lastReceivedBlockTime', 'latency', 'avg5LastLatency', 'connections']
    data = []

    for i in range(number_of_nodes):
        temp_list = []
        temp_list.extend(
            [f'Node {i}', nodes[f'node_{i}']['lastBlockTime'], nodes[f'node_{i}']['lastReceivedBlockTime'],
             nodes[f'node_{i}']['latency'], nodes[f'node_{i}']['avgLatencyRecords'], nodes[f'node_{i}']['numberOfConnections']])
        data.append(temp_list)

    print(tabulate(data, headers))
    print('')
    print(f'Time to next epoch: {str(datetime.timedelta(seconds=round(diff_epoch_end_seconds)))}')
    print('')

    if not current_leader < 0:
        print(f"Number of blocks this epoch: {len(nodes[f'node_{current_leader}']['leadersLogs'])}")
        if is_in_transition:
            print('All nodes are currently leaders while no nodes has been elected for block creation')
        elif not nodes[f'node_{current_leader}']['leadersLogs']:
            print('No blocks this epoch')
        else:
            next_block_time = max_time = int(time.time()) + 86400 # + Max epoch time in seconds # TODO: change this to time.time() + slotDuration * slotPerEpoch
            for log in nodes[f'node_{current_leader}']['leadersLogs']:
                scheduled_at_time = datetime.datetime.strptime(re.sub(r"([\+-]\d\d):(\d\d)(?::(\d\d(?:.\d+)?))?", r"\1\2\3", log['scheduled_at_time']), "%Y-%m-%dT%H:%M:%S%z").timestamp()
                if int(time.time()) < scheduled_at_time < next_block_time:
                    next_block_time = scheduled_at_time

            if next_block_time == max_time:
                print('No more blocks this epoch')
            else:
                print(f"Time to next block creation: {str(datetime.timedelta(seconds=round(next_block_time - int(time.time()))))}")

    print('________________________________')


def send_my_tip():
    threading.Timer(SEND_MY_TIP_INTERVAL, send_my_tip).start()

    global pooltoolmax

    if current_leader < 0:
        return

    ip_address, port = stakepool_config['rest']['listen'].split(':')
    try:
        stats = yaml.safe_load(subprocess.check_output(
            [jcli_call_format, 'rest', 'v0', 'block', nodes[f'node_{current_leader}']['lastBlockHash'], 'get',
             '-h',
             f'http://{ip_address}:{int(port) + current_leader}/api']).decode(
            'utf-8'))

        PARAMS = {'poolid': pool_id, 'userid': user_id, 'genesispref': genesis_hash,
                  'mytip': nodes[f'node_{current_leader}']['lastBlockHeight'],
                  'lasthash': nodes[f'node_{current_leader}']['lastBlockHash'], 'lastpool': stats[168:168 + 64],
                  'lastParent': stats[104:104 + 64], 'lastSlot': f'0x{stats[24:24 + 8]}',
                  'lastEpoch': f'0x{stats[16:16 + 8]}'}
        # sending get request and saving the response as response object
        r = requests.get(url=url, params=PARAMS)

        # extracting data in json format
        data = r.json()
        if data['success'] and data['confidence']:
            pooltoolmax = int(data['pooltoolmax'])

    except subprocess.CalledProcessError as e:
        pass


is_in_transition = False
diff_epoch_end_seconds = 0


def get_network_stats(node_number):
    ip_address , port = stakepool_config['rest']['listen'].split(':')
    try:
        output = yaml.safe_load(
                subprocess.check_output([jcli_call_format , 'rest' , 'v0' , 'network' , 'stats' , 'get' , '-h' ,
                                f'http://{ip_address}:{int(port) + node_number}/api']).decode('utf-8'))
    except subprocess.CalledProcessError as e:
        return []
    return output


def get_leaders_logs(node_number):
    ip_address , port = stakepool_config['rest']['listen'].split(':')
    try:
        output = yaml.safe_load(
            subprocess.check_output([jcli_call_format, 'rest', 'v0', 'leaders', 'logs', 'get', '-h',
                                     f'http://{ip_address}:{int(port) + node_number}/api']).decode('utf-8'))
    except subprocess.CalledProcessError as e:
        return []
    return output


def wait_for_leaders_logs():
    for i in range(number_of_nodes):
        while 'wake_at_time:' not in nodes[f'node_{i}']['leadersLogs']:
            nodes[f'node_{i}']['leadersLogs'] = get_leaders_logs(i)
            time.sleep(1)


settings = {}
is_new_epoch = True


# This method is based on
# https://github.com/rdlrt/Alternate-Jormungandr-Testnet/blob/master/scripts/jormungandr-leaders-failover.sh
def check_transition():
    threading.Timer(TRANSITION_CHECK_INTERVAL, check_transition).start()
    global is_in_transition
    global diff_epoch_end_seconds
    global settings
    global is_new_epoch

    if current_leader < 0 or is_in_transition:
        return

    ip_address, port = stakepool_config['rest']['listen'].split(':')

    if is_new_epoch:
        try:
            settings = yaml.safe_load(subprocess.check_output(
                [jcli_call_format, 'rest', 'v0', 'settings', 'get', '-h',
                 f'http://{ip_address}:{int(port) + current_leader}/api']))
            is_new_epoch = False

        except subprocess.CalledProcessError as e:
            return

    slot_duration = int(settings['slotDuration'])
    slots_per_epoch = int(settings['slotsPerEpoch'])

    curr_slot = (((int(time.time()) - 1576264417) % (slots_per_epoch * slot_duration)) / slot_duration)
    diff_epoch_end = slots_per_epoch - curr_slot
    diff_epoch_end_seconds = diff_epoch_end * slot_duration

    if diff_epoch_end < slot_duration + TRANSITION_CHECK_INTERVAL:  # Adds a small probability of creating an adversarial fork
        is_in_transition = True
        print("Electing all nodes as leaders for epoch transition:")

        for i in range(number_of_nodes):
            try:
                if not i == current_leader:
                    subprocess.run([jcli_call_format, 'rest', 'v0', 'leaders', 'post', '-f', node_secret_path, '-h',
                                    f'http://{ip_address}:{int(port) + i}/api'])
            except subprocess.CalledProcessError as e:
                continue

        # Wait until new epoch
        time.sleep(slot_duration + TRANSITION_CHECK_INTERVAL - 1)

        wait_for_leaders_logs()  # This is an infinite loop, if the nodes are not elected for any blocks.

        for i in range(number_of_nodes):
            try:
                # Delete leaders except one
                if not i == current_leader:
                    subprocess.run([jcli_call_format, 'rest', 'v0', 'leaders', 'delete', '1', '-h',
                                    f'http://{ip_address}:{int(port) + i}/api'])

            except subprocess.CalledProcessError as e:
                continue

        is_new_epoch = True
        is_in_transition = False


# Make sure only one node is leader. (only for safety reasons)! This should be done regularly.
# Though this should never happen.
def leaders_check():
    threading.Timer(LEADERS_CHECK_INTERVAL, leaders_check).start()

    if is_in_transition:
        return

    ip_address, port = stakepool_config['rest']['listen'].split(':')

    max_retries = 5

    for i in range(number_of_nodes):
        if current_leader == i or nodes[f'node_{i}']['state'] != 'Running':
            continue

        try:
            for leader_id in yaml.safe_load(subprocess.check_output(
                    [jcli_call_format, 'rest', 'v0', 'leaders', 'get', '-h',
                     f'http://{ip_address}:{int(port) + i}/api']).decode('utf-8')):

                for retry in range(max_retries):
                    try:
                        subprocess.run([jcli_call_format, 'rest', 'v0', 'leaders', 'delete', f'{leader_id}', '-h',
                                        f'http://{ip_address}:{int(port) + i}/api'])
                        break
                    except subprocess.CalledProcessError as e:
                        pass
                    if retry == max_retries - 1:
                        print('kill process')
                        # TODO: If it ends here, jcli is down -> and a restart is needed.... BUT, is this extra safety needed?
                        break
                    time.sleep(1)

        except subprocess.CalledProcessError as e:
            pass


def clear():
    # check and make call for specific operating system
    _ = subprocess.call(['clear' if os.name == 'posix' else 'cls'])


def main():
    # Start nodes
    start_nodes()

    # Begin threads
    update_nodes_info()
    leader_election()
    table_update()
    stuck_check()
    send_my_tip()
    check_transition()
    leaders_check()


if __name__ == "__main__":
    main()
