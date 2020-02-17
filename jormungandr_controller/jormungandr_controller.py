import copy
import datetime
import json
import os
import collections
import subprocess
import threading
import time
import re
import urllib
import string
import locale

import requests
import yaml
from tabulate import tabulate
import telegram

config = json.load(open('my_config.json', 'r'))

#### Configuration ####
jcli_call_format = config['Configuration']['jcli_call_format']
jormungandr_call_format = config['Configuration']['jormungandr_call_format']
stakepool_config_path = config['Configuration']['stakepool_config_path']
node_secret_path = config['Configuration']['node_secret_path']
genesis_hash = config['Configuration']['genesis_hash']
pool_id = config['Configuration']['pool_id']
number_of_nodes = config['Configuration']['number_of_nodes']
# Pooltool sendmytip setup #
if config['PooltoolSetup']['activate']:
    url = config['PooltoolSetup']['url']
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
# Telegram Bot setup
if config['TelegramBot']['activate']:
    token = config['TelegramBot']['token']
    chat_id = config['TelegramBot']['chat_id']
#######################

# _________________________________________________________________________________________________________________#

# !DON'T TOUCH THESE VARIABLES! #
locale.setlocale(locale.LC_ALL, '')
stakepool_config = yaml.safe_load(open(stakepool_config_path, 'r'))
tmp_config_file_path = 'tmp.config'
current_leader = -1
pooltoolmax = 0
nodes = {}
next_block = {'scheduled_at_time_string': '', 'scheduled_at_time_epoch': 0, 'wait_block_time_change': False}
total_blocks_this_epoch = 0
blocks_made_this_epoch = 0


def node_init(node_number):
    global nodes
    nodes[f'node_{node_number}'] = {}
    # Start a jormungandr process
    f = open(f'log_{node_number}', 'w')
    nodes[f'node_{node_number}']['process_id'] = subprocess.Popen(
        [jormungandr_call_format, '--genesis-block-hash', genesis_hash, '--config', tmp_config_file_path, '--secret',
         node_secret_path], stdout=f, stderr=subprocess.STDOUT)#subprocess.DEVNULL
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
    nodes[f'node_{node_number}']['lastTgNotified'] = time.time()


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


def on_start_node_info():
    global nodes

    for i in range(number_of_nodes):

        if nodes[f'node_{i}']['state'] != 'Running':
            threading.Timer(30, on_start_node_info).start()
            return

    for i in range(number_of_nodes):
        nodes[f'node_{i}']['leadersLogs'] = get_leaders_logs(i)


num_connection_update = 0
leaders_log_update = 0
validate_block_timer = 0
new_block_minted = False
block_minted_update = 0


def update_nodes_info():
    global nodes
    global num_connection_update
    global validate_block_timer
    global leaders_log_update
    global blocks_made_this_epoch
    global new_block_minted
    global block_minted_update

    ip_address, port = stakepool_config['rest']['listen'].split(':')

    for i in range(number_of_nodes):
        try:

            node_stats = yaml.safe_load(subprocess.check_output(
                [jcli_call_format, 'rest', 'v0', 'node', 'stats', 'get', '-h',
                 f'http://{ip_address}:{int(port) + i}/api']).decode(
                'utf-8'))

            if node_stats['state'] == 'Running':
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

            elif node_stats['state'] == 'Bootstrapping':
                nodes[f'node_{i}']['lastBlockHeight'] = 0
                nodes[f'node_{i}']['lastBlockHash'] = ''
                nodes[f'node_{i}']['state'] = 'Bootstrapping'

        except subprocess.CalledProcessError as e:
            nodes[f'node_{i}']['lastBlockHeight'] = 0
            nodes[f'node_{i}']['lastBlockHash'] = ''
            nodes[f'node_{i}']['state'] = 'Starting'
            continue

    num_connection_update += 1
    if num_connection_update >= 20:
        num_connection_update = 0
        for i in range(number_of_nodes):
            try:
                if nodes[f'node_{i}']['state'] == 'Running':
                    network_stats = get_network_stats(i)
                    nodes[f'node_{i}']['numberOfConnections'] = len(network_stats)
            except subprocess.CalledProcessError as e:
                print('Could not get network stats')
                continue

    if not current_leader < 0:
        # test()
        leaders_log_update += 1
        if leaders_log_update >= 60:
            leaders_log_update = 0
            update_leaders_logs()
        get_next_block_time()

    block_minted_update += 1
    if block_minted_update >= 60:
        block_minted_update = 0
        # Check if a new block is made
        blocks_this_epoch = get_blocks_made_this_epoch()
        if blocks_this_epoch > blocks_made_this_epoch:
            blocks_made_this_epoch = blocks_this_epoch
            new_block_minted = True

    threading.Timer(UPDATE_NODES_INTERVAL, update_nodes_info).start()


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
        elif highest_blockheight == nodes[f'node_{i}']['lastBlockHeight'] and lowest_latency > nodes[f'node_{i}'][
            'avgLatencyRecords']:
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
            try:
                subprocess.run([jcli_call_format, 'rest', 'v0', 'leaders', 'delete', '1', '-h',
                                f'http://{ip_address}:{int(port) + current_leader}/api'])
            except subprocess.CalledProcessError as e:
                print("Could not delete old leader")

        # Update current leader
        current_leader = healthiest_node

    threading.Timer(LEADER_ELECTION_INTERVAL, leader_election).start()


def stuck_check():
    threading.Timer(STUCK_CHECK_INTERVAL, stuck_check).start()

    global nodes

    for i in range(number_of_nodes):

        if int(time.time()) - nodes[f'node_{i}']['timeSinceLastBlock'] > LAST_SYNC_RESTART and nodes[f'node_{i}'][
            'state'] == 'Bootstrapping':
            print(f'Node {i} is restarting due to stuck in bootstrapping')
            # Kill process
            nodes[f'node_{i}']['process_id'].kill()
            # Give it some time to shutdown
            time.sleep(5)
            # Start a jormungandr process
            start_node(i)


def update_leaders_logs():
    for i in range(number_of_nodes):
        nodes[f'node_{i}']['leadersLogs'] = get_leaders_logs(i)


def time_between(d1, d2):
    d1 = datetime.datetime.strptime(d1, "%Y-%m-%dT%H:%M:%S%z")
    d2 = datetime.datetime.strptime(d2, "%Y-%m-%dT%H:%M:%S%z")
    return (d2 - d1).total_seconds()


def table_update():
    threading.Timer(TABLE_UPDATE_INTERVAL, table_update).start()

    global scheduled_at_time_string

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
    print('-')

    headers = ['Node', 'lastBlockTime', 'lastReceivedBlockTime', 'latency', 'avg5LastLatency', 'connections']
    data = []

    for i in range(number_of_nodes):
        temp_list = []
        temp_list.extend(
            [f'Node {i}', nodes[f'node_{i}']['lastBlockTime'], nodes[f'node_{i}']['lastReceivedBlockTime'],
             nodes[f'node_{i}']['latency'], nodes[f'node_{i}']['avgLatencyRecords'],
             nodes[f'node_{i}']['numberOfConnections']])
        data.append(temp_list)

    print(tabulate(data, headers))
    print('-')
    print(f'Time to next epoch: {str(datetime.timedelta(seconds=round(diff_epoch_end_seconds)))}')

    if not current_leader < 0:
        if is_in_transition:
            print('All nodes are currently leaders while no nodes has been elected for block creation')
        elif not nodes[f'node_{current_leader}']['leadersLogs']:
            print('No blocks this epoch')
        else:
            if next_block['scheduled_at_time_epoch'] == 0:
                print('No more blocks this epoch')
            else:
                print(
                    f"Time to your next block: {str(datetime.timedelta(seconds=round(next_block['scheduled_at_time_epoch'] - int(time.time()))))}")
        print(f"Number of total blocks this epoch: {total_blocks_this_epoch}")
        print(f'Number of minted blocks this epoch: {blocks_made_this_epoch}')
        counter = 0
        for i in range(len(nodes[f'node_{current_leader}']['leadersLogs'])):
            if 'Pending' == nodes[f'node_{current_leader}']['leadersLogs'][i]['status']:
                counter += 1
        print(f"Number of blocks left this epoch: {counter}")


def get_next_block_time():
    global next_block

    next_block_epoch = max_time = int(
        time.time()) + 86400  # + Max epoch time in seconds # TODO: change this to time.time() + slotDuration * slotPerEpoch

    for log in nodes[f'node_{current_leader}']['leadersLogs']:

        scheduled_at_time = datetime.datetime.strptime(
            re.sub(r"([\+-]\d\d):(\d\d)(?::(\d\d(?:.\d+)?))?", r"\1\2\3", log['scheduled_at_time']),
            "%Y-%m-%dT%H:%M:%S%z").timestamp()

        if int(time.time()) < scheduled_at_time < next_block_epoch:

            next_block_epoch = round(scheduled_at_time)

            if next_block_epoch != next_block['scheduled_at_time_epoch']:

                next_block['scheduled_at_time_epoch'] = next_block_epoch

    if next_block_epoch == max_time:
        next_block['scheduled_at_time_epoch'] = 0


def send_my_tip():
    threading.Timer(SEND_MY_TIP_INTERVAL, send_my_tip).start()

    global pooltoolmax
    global url

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

        platform = urllib.parse.urlencode({"platform": "jormungandr_controller.py"})

        # sending get request and saving the response as response object
        r = requests.get(url=url + '?' + platform, params=PARAMS)

        # extracting data in json format
        data = r.json()
        if data['success'] and data['confidence']:
            pooltoolmax = int(data['pooltoolmax'])

    except subprocess.CalledProcessError as e:
        pass


def get_stakepool(node_number):
    ip_address, port = stakepool_config['rest']['listen'].split(':')
    try:
        output = yaml.safe_load(
            subprocess.check_output([jcli_call_format, 'rest', 'v0', 'stake-pool', 'get', pool_id, '-h',
                                     f'http://{ip_address}:{int(port) + node_number}/api']).decode('utf-8'))
    except subprocess.CalledProcessError as e:
        return []
    return output


def shutdown_node(node_number):
    ip_address, port = stakepool_config['rest']['listen'].split(':')
    try:
        output = subprocess.check_output([jcli_call_format, 'rest', 'v0', 'shutdown', 'get', '-h',
                                          f'http://{ip_address}:{int(port) + node_number}/api']).decode('utf-8')
    except subprocess.CalledProcessError as e:
        return ''
    return output


is_in_transition = False
diff_epoch_end_seconds = 0


def get_network_stats(node_number):
    ip_address, port = stakepool_config['rest']['listen'].split(':')
    try:
        output = yaml.safe_load(
            subprocess.check_output([jcli_call_format, 'rest', 'v0', 'network', 'stats', 'get', '-h',
                                     f'http://{ip_address}:{int(port) + node_number}/api']).decode('utf-8'))
    except subprocess.CalledProcessError as e:
        return []
    return output


def get_leaders_logs(node_number):
    ip_address, port = stakepool_config['rest']['listen'].split(':')
    try:
        output = yaml.safe_load(
            subprocess.check_output([jcli_call_format, 'rest', 'v0', 'leaders', 'logs', 'get', '-h',
                                     f'http://{ip_address}:{int(port) + node_number}/api']).decode('utf-8'))
    except subprocess.CalledProcessError as e:
        return []
    return output


def is_leaders_logs_not_empty(node_number):
    for field in nodes[f'node_{node_number}']['leadersLogs']:
        if 'wake_at_time' in field:
            return True
    return False


def wait_for_leaders_logs():
    global nodes
    global total_blocks_this_epoch

    for i in range(number_of_nodes):

        start_timer = time.time()

        while 1:
            if is_leaders_logs_not_empty(i):
                break

            nodes[f'node_{i}']['leadersLogs'] = get_leaders_logs(i)
            time.sleep(1)

            if start_timer + 20 < time.time():
                break


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
    global total_blocks_this_epoch
    global blocks_made_this_epoch
    global known_blocks

    if current_leader < 0:
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

    if is_in_transition:
        return

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

        known_blocks = []
        is_new_epoch = True
        is_in_transition = False

        # Wait some time to make sure that leaders logs are a complete list
        time.sleep(60)
        update_leaders_logs()
        for i in range(number_of_nodes):
            print(f"Node {i}: \n {nodes[f'node_{i}']['leadersLogs']}")
            if config['TelegramBot']['activate']:
                send_telegram_message(f"Node {i} has {len(nodes[f'node_{i}']['leadersLogs'])} blocks assigned")
        total_blocks_this_epoch = len(nodes[f'node_{current_leader}']['leadersLogs'])
        blocks_made_this_epoch = 0


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


last_message_update_id = 0
current_total_stake = 0


def send_telegram_message(message):
    bot = telegram.Bot(token=token)
    bot.sendMessage(chat_id=chat_id, text=message)


def telegram_notifier():
    threading.Timer(10, telegram_notifier).start()

    global last_message_update_id
    global current_total_stake
    global blocks_made_this_epoch
    global new_block_minted

    bot = telegram.Bot(token=token)

    # Notify if out of sync for more than 1000 sec
    for i in range(number_of_nodes):
        if time.time() - nodes[f'node_{i}']['timeSinceLastBlock'] > 1000 and nodes[f'node_{i}'][
            'lastTgNotified'] + 600 < time.time():
            bot.sendMessage(chat_id=chat_id,
                            text=f"Node {i} has not been in sync for {round(time.time() - nodes[f'node_{i}']['timeSinceLastBlock'])} seconds")
            nodes[f'node_{i}']['lastTgNotified'] = time.time()

    # Notifidy if current stake has changed
    if not current_leader < 0:
        total_stake = round(int(get_stakepool(current_leader)['total_stake']) / 1000000)

        if current_total_stake > total_stake:
            current_total_stake = total_stake

            bot.sendMessage(chat_id=chat_id,
                            text=f'Your total stake has been reduced to {current_total_stake:n} ADA')

        elif current_total_stake < total_stake:
            current_total_stake = total_stake

            bot.sendMessage(chat_id=chat_id,
                            text=f'Your total stake has increased to {current_total_stake:n} ADA')

    if new_block_minted:
        bot.sendMessage(chat_id=chat_id,
                        text=f'Pooltool; You just minted a new block! Total blocks minted this epoch: {blocks_made_this_epoch}')
        new_block_minted = False

    updates = bot.get_updates(offset=last_message_update_id + 1)
    if not updates:
        return

    last_message_received = updates[len(updates) - 1]
    last_message_update_id = last_message_received['update_id']

    if 'restart' in last_message_received['message']['text'].lower():
        node = [int(s) for s in last_message_received['message']['text'].split() if s.isdigit()][0]
        if node > number_of_nodes - 1:
            bot.sendMessage(chat_id=chat_id,
                            text=f'No nodes with that number')
            return

        bot.sendMessage(chat_id=chat_id,
                        text=f'Shutting down node {node}...')
        if shutdown_node(node) != 'Success\n':
            nodes[f'node_{node}']['process_id'].kill()
        time.sleep(5)
        start_node(node)
        on_start_node_info()

        bot.sendMessage(chat_id=chat_id,
                        text=f'Starting node {node}...')


def clear():
    # check and make call for specific operating system
    _ = subprocess.call(['clear' if os.name == 'posix' else 'cls'])


def get_next_block_hash(
        block_hash):  # ./jcli rest v0 block e207f3e6cd6f76340f59b214bff4508f8cb80329f812e082a2bb4c2c7f4e0a88 next-id get —host
    ip_address, port = stakepool_config['rest']['listen'].split(':')
    try:
        output = subprocess.check_output([jcli_call_format, 'rest', 'v0', 'block', block_hash, 'next-id', 'get', '-h',
                                          f'http://{ip_address}:{int(port) + current_leader}/api']).decode(
            'utf-8').replace('\n', '')
    except subprocess.CalledProcessError as e:
        return 'error'
    return output


def get_block_hash_from_leaders_logs():
    global next_block

    for i in range(len(nodes[f'node_{current_leader}']['leadersLogs'])):

        if next_block['scheduled_at_time_string'] == nodes[f'node_{current_leader}']['leadersLogs'][i][
            'scheduled_at_time']:
            if 'Rejected' == nodes[f'node_{current_leader}']['leadersLogs'][i]['status']:
                send_telegram_message(nodes[f'node_{current_leader}']['leadersLogs'][i]['status']['reason'])
                next_block['wait_block_time_change'] = False
            if 'Block' == nodes[f'node_{current_leader}']['leadersLogs'][i]['status']:
                block_hash = nodes[f'node_{current_leader}']['leadersLogs'][i]['status']['Block']['block']
                print(block_hash)
                string_test = get_next_block_hash(block_hash)
                if string_test == 'error':
                    print('block lost')
                    send_telegram_message('You just lost a block')
                    next_block['wait_block_time_change'] = False
                if all(c in string.hexdigits for c in string_test):
                    print('Block won')
                    send_telegram_message('test mesthod: You just won a block')
                    next_block['wait_block_time_change'] = False
                print(string_test)
                print(type(string_test))
            else:
                return


def get_blocks_made_this_epoch():
    url2 = f'https://pooltool.s3-us-west-2.amazonaws.com/8e4d2a3/pools/{pool_id}/livestats.json'
    try:
        r = requests.get(url=url2)
    except requests.exceptions.RequestException as e:
        return 0
    return r.json()['epochblocks']


def set_variables_on_start():
    global blocks_made_this_epoch

    blocks_made_this_epoch = get_blocks_made_this_epoch()


known_blocks = []


# This method is a test...
def check_new_blocks_minted():
    threading.Timer(60, check_new_blocks_minted).start()
    global known_blocks
    global blocks_made_this_epoch

    if current_leader < 0:
        return

    for l in nodes[f'node_{current_leader}']['leadersLogs']:
        print(l['status'])
        if l['status'] != 'Pending':

            if l['scheduled_at_time'] in known_blocks:
                continue

            if l['status'] == 'Block':
                block_hash = l['status']['Block']['block']
                print(block_hash)
                response = get_next_block_hash(block_hash)

                if response == 'error':
                    print('block lost')
                    send_telegram_message('test mesthod: You just lost a block')
                    known_blocks.append(l['scheduled_at_time'])

                elif all(c in string.hexdigits for c in response):
                    print('Block won')
                    send_telegram_message('test mesthod: You just won a block')
                    known_blocks.append(l['scheduled_at_time'])
                    blocks_made_this_epoch += 1

            elif l['status'] == 'Rejected':
                send_telegram_message(f"test mesthod: Block got rejected with message: {l['status']['Rejected']}")
                known_blocks.append(l['scheduled_at_time'])


def main():
    # Start nodes
    start_nodes()

    set_variables_on_start()
    # on_start_node_info()

    # Begin threads
    update_nodes_info()
    leader_election()
    table_update()
    stuck_check()
    check_transition()
    leaders_check()
    # check_new_blocks_minted()

    if config['PooltoolSetup']['activate']:
        send_my_tip()
    if config['TelegramBot']['activate']:
        telegram_notifier()


if __name__ == "__main__":
    main()
