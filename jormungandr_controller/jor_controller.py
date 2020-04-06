import threading
import datetime
import locale
import copy
import json
import yaml
import time
import re

from modules.node import Node
from modules.configuration import Config
from modules.printer import Printer
from modules.pooltool import Pooltool
from modules.telegram_bot import TelegramBot

locale.setlocale(locale.LC_ALL, '')


class JorController:

    def __init__(self):
        self.conf = Config()
        self.printer = Printer()
        self.pooltool = Pooltool(self.conf.pool_id)
        if self.conf.telegrambot_active:
            self.telegram = TelegramBot(self.conf.token, self.conf.chat_id)

        self.nodes = []
        self.current_leader = -1
        self.next_block_time = 0
        self.blocks_minted_this_epoch = 0
        self.total_blocks_this_epoch = 0
        self.blocks_left_this_epoch = 0

        self.is_in_transition = False
        self.is_new_epoch = True
        self.known_blocks = []

        self.diff_epoch_end_seconds = 0
        self.slot_duration = 0
        self.slots_per_epoch = 0

        self.current_total_stake = 0
        self.new_block_minted = False

    def start_node(self, node_number):
        # Use a temp copy of stakepool_config
        stakepool_config_temp = copy.deepcopy(yaml.safe_load(open(self.conf.stakepool_config_path, 'r')))

        tmp_config_file_path = 'tmp_config.json'

        # Create a temporarily file, as jormungandr require this as input
        with open(tmp_config_file_path, 'w') as tmp_config_file:
            # Increase port number for specific node
            ip_address, port = stakepool_config_temp['rest']['listen'].split(':')
            stakepool_config_temp['rest']['listen'] = ip_address + ':' + str(int(port) + node_number)
            # Listen_address
            x, ip, ip_address, comm_p, port = stakepool_config_temp['p2p']['listen_address'].split('/')
            stakepool_config_temp['p2p'][
                'listen_address'] = f'/{ip}/{ip_address}/{comm_p}/{int(port) + node_number}'
            # Public_address
            x, ip, ip_address, comm_p, port = stakepool_config_temp['p2p']['public_address'].split('/')
            stakepool_config_temp['p2p'][
                'public_address'] = f'/{ip}/{ip_address}/{comm_p}/{int(port) + node_number}'
            if self.conf.use_seperate_storage:
                storage = stakepool_config_temp['storage']
                stakepool_config_temp['storage'] = f'{storage}_{node_number}'
            # Save in temp config file
            json.dump(stakepool_config_temp, tmp_config_file)

        print(f'Starting node {node_number}...')

        return Node(node_number, self.conf.jcli_call_format, self.conf.jormungandr_call_format, self.conf.genesis_hash,
                    tmp_config_file_path, self.conf.node_secret_path)

    def read_node_output(self, node):
        while True:
            line = node.get_node_output()
            if self.conf.log_to_file:
                node.write_log_file(line.decode('utf-8'))
            if self.conf.stuck_check_active:
                self.stuck_check(line, node)
            if not node.log_thread_running:
                break

    def start_nodes(self):
        for i in range(self.conf.number_of_nodes):
            self.nodes.append(self.start_node(i))
            if self.conf.log_to_file or self.conf.stuck_check_active:
                thread = threading.Thread(target=self.read_node_output, args=(self.nodes[i],))
                self.nodes[i].log_thread_running = True
                thread.start()
            time.sleep(5)

    def restart_node(self, unique_id):
        if self.conf.telegrambot_active:
            self.telegram.send_message(f'Shutting down node {unique_id}...')

        if self.nodes[unique_id].shutdown_node() != 'Success\n':
            print('Could not shutdown properly')
        time.sleep(10)
        # Sometimes shutdown does not kill the node completely, so insure this by killing process
        self.nodes[unique_id].process_id.kill()
        self.nodes[unique_id] = self.start_node(unique_id)
        if self.conf.log_to_file or self.conf.stuck_check_active:
            thread = threading.Thread(target=self.read_node_output, args=(self.nodes[unique_id],))
            self.nodes[unique_id].log_thread_running = True
            thread.start()
        # TODO: Does this node needs some data to be initialized after reboot?

        if self.conf.telegrambot_active:
            self.telegram.send_message(f'Starting node {unique_id}...')

    def update_next_block_time(self):
        next_block_time_tmp = max_time = int(time.time()) + self.slot_duration * self.slots_per_epoch

        for log in self.nodes[self.current_leader].leaders.leaders_logs:
            if not log:
                continue

            scheduled_at_time = datetime.datetime.strptime(
                re.sub(r"([\+-]\d\d):(\d\d)(?::(\d\d(?:.\d+)?))?", r"\1\2\3", log['scheduled_at_time']),
                "%Y-%m-%dT%H:%M:%S%z").timestamp()

            if int(time.time()) < scheduled_at_time < next_block_time_tmp:

                next_block_time_tmp = round(scheduled_at_time)

                if next_block_time_tmp != self.next_block_time:
                    self.next_block_time = next_block_time_tmp

        if next_block_time_tmp == max_time:
            self.next_block_time = 0

    def update_blocks_minted(self):
        # Check if a new block is made
        livestats = self.pooltool.pooltool_livestats()
        stats = self.pooltool.pooltool_stats()
        if livestats == {} or stats == {} or self.current_leader < 0:
            return

        current_epoch = int(self.nodes[self.current_leader].node_stats.lastBlockDate.split('.')[0])
        blocks_this_epoch = livestats['epochblocks']
        current_epoch_livestat = livestats['lastBlockEpoch']

        if current_epoch_livestat == current_epoch:
            if blocks_this_epoch > self.blocks_minted_this_epoch:
                self.blocks_minted_this_epoch = blocks_this_epoch
                if self.conf.telegrambot_active:
                    self.telegram.send_message(
                        f'Pooltool; New block minted! Total blocks minted this epoch: {self.blocks_minted_this_epoch}')
        else:
            self.blocks_minted_this_epoch = 0

    def leader_election(self):
        healthiest_node = -1
        highest_blockheight = 0
        lowest_latency = 10000

        # Find healthiest node
        for node in self.nodes:

            if highest_blockheight < node.node_stats.lastBlockHeight:
                highest_blockheight = node.node_stats.lastBlockHeight
                lowest_latency = node.avgLatencyRecords
                healthiest_node = node.unique_id
                continue
            elif highest_blockheight == node.node_stats.lastBlockHeight and lowest_latency > node.avgLatencyRecords:
                lowest_latency = node.avgLatencyRecords
                healthiest_node = node.unique_id

        if self.current_leader != healthiest_node and not self.is_in_transition and healthiest_node >= 0:
            print(f'Changing leader from {self.current_leader} to {healthiest_node}')

            if not self.nodes[healthiest_node].set_leader(self.conf.node_secret_path):
                print("Could not elect new leader, skipping")
                return

            if not self.current_leader < 0:
                if not self.nodes[self.current_leader].delete_leader(1):
                    print("Could not delete old leader")

            # Update current leader
            self.current_leader = healthiest_node

    def bootstrap_stuck_check(self):
        for node in self.nodes:
            if int(time.time()) - node.timeSinceLastBlock > 30 and node.node_stats.state == 'Starting':
                print(f'Node {node.unique_id} is restarting due to stuck in starting')
                self.restart_node(node.unique_id)
            if int(time.time()) - node.timeSinceLastBlock > self.conf.LAST_SYNC_RESTART and \
                    (node.node_stats.state == 'Bootstrapping'):
                print(f'Node {node.unique_id} is restarting due to stuck in bootstrapping')
                self.restart_node(node.unique_id)

    def send_my_tip(self):
        if self.current_leader < 0:
            return
        self.pooltool.pooltool_send_my_tip(self.conf.user_id, self.conf.genesis_hash,
                                           self.nodes[self.current_leader].node_stats.lastBlockHeight,
                                           self.nodes[self.current_leader].node_stats.lastBlockHash,
                                           self.nodes[self.current_leader].get_block())

    def is_leaders_logs_not_empty(self, node_number):
        for field in self.nodes[node_number].leaders.leaders_logs:
            if 'wake_at_time' in field:
                return True
        return False

    def wait_for_leaders_logs(self):
        for i in range(len(self.nodes)):
            start_timer = time.time()
            while 1:
                self.nodes[i].update_leaders_logs()
                if self.is_leaders_logs_not_empty(i):
                    break
                time.sleep(1)
                if start_timer + 60 < time.time():
                    break

    def utc_offset(self, time, offset):
        def pad(number):
            n = str(abs(number))

            while len(n) < 2:
                n = "0" + n

            if number >= 0:
                n = "+" + n
            else:
                n = "-" + n
            return n

        utc_diff_format = f"{pad(offset)}:00"

        time = list(time)
        i = time.index("+")
        time[i:] = list(utc_diff_format)
        time = ''.join(time)

        return time

    def send_block_schedule(self):
        list_schedule_unix = []
        if not self.nodes[self.current_leader].leaders.leaders_logs:
            return
        for log in self.nodes[self.current_leader].leaders.leaders_logs:
            if log['status'] == 'Pending':
                obj = datetime.datetime.strptime(
                    re.sub(r"([\+-]\d\d):(\d\d)(?::(\d\d(?:.\d+)?))?", r"\1\2\3",
                           self.utc_offset(log['scheduled_at_time'], self.conf.utc_diff)),
                    "%Y-%m-%dT%H:%M:%S%z")
                obj = obj - datetime.timedelta(hours=-self.conf.utc_diff)
                list_schedule_unix.append(
                    str(obj)
                )
        list_schedule_unix.sort()
        msg = ''
        counter = 1
        for l in list_schedule_unix:
            msg = msg + f'Block {counter}: ' + l + '\n'
            counter += 1
        self.telegram.send_message(msg)

    def sort_leaders_log_to_current_epoch_only(self, logs, current_epoch):
        sorted_log = []
        for log in logs:
            if int(log['scheduled_at_date'][:2]) == current_epoch:
                sorted_log.append(log)
        return sorted_log

    def on_new_epoch(self):
        self.known_blocks = []
        self.is_new_epoch = True

        # Wait some time to make sure that leaders logs are a complete list and force update
        time.sleep(60)
        for node in self.nodes:
            node.update_leaders_logs()
            if self.conf.telegrambot_active:
                self.telegram.send_message(
                    f"Node {node.unique_id} has {node.leaders.pending} blocks assigned")

        if self.conf.telegrambot_active:
            self.send_block_schedule()
        self.total_blocks_this_epoch = self.blocks_left_this_epoch = self.nodes[self.current_leader].leaders.pending
        if self.conf.send_slots:
            self.pooltool.pooltool_send_slots(
                self.sort_leaders_log_to_current_epoch_only(self.nodes[self.current_leader].leaders.leaders_logs, int(self.nodes[self.current_leader].node_stats.lastBlockDate.split('.')[0])),
                int(self.nodes[self.current_leader].node_stats.lastBlockDate.split('.')[0]), self.conf.user_id,
                self.conf.genesis_hash)
        self.is_in_transition = False

    # This method is based on
    # https://github.com/rdlrt/Alternate-Jormungandr-Testnet/blob/master/scripts/jormungandr-leaders-failover.sh
    def check_transition(self):
        if self.current_leader < 0:
            return

        if self.is_new_epoch:
            # If new epoch, update settings
            self.nodes[self.current_leader].update_settings()
            self.slot_duration = self.nodes[self.current_leader].settings.slot_duration
            self.slots_per_epoch = self.nodes[self.current_leader].settings.slots_per_epoch
            self.is_new_epoch = False

        curr_slot = (((int(time.time()) - 1576264417) % (
                self.slots_per_epoch * self.slot_duration)) / self.slot_duration)
        diff_epoch_end = self.slots_per_epoch - curr_slot
        self.diff_epoch_end_seconds = diff_epoch_end * self.slot_duration

        if self.is_in_transition:
            return

        if diff_epoch_end < self.slot_duration + self.conf.TRANSITION_CHECK_INTERVAL:  # Adds a small probability of creating an adversarial fork
            self.is_in_transition = True
            print("Electing all nodes as leaders for epoch transition:")

            for node in self.nodes:
                # Set all nodes as leader except current leader
                if not node.unique_id == self.current_leader:
                    if not node.set_leader(self.conf.node_secret_path):
                        continue

            # Wait until new epoch
            time.sleep(self.slot_duration + self.conf.TRANSITION_CHECK_INTERVAL - 1)

            self.wait_for_leaders_logs()  # 60 sec timeout loop, if the nodes are not elected for any blocks.

            for node in self.nodes:
                # Delete leaders except one
                if not node.unique_id == self.current_leader:
                    if not node.delete_leader(1):
                        continue

            self.on_new_epoch()

    # Make sure only one node is leader. (only for safety reasons)! This should be done regularly.
    # Though this should never happen.
    def leaders_check(self):
        if self.is_in_transition:
            return

        for node in self.nodes:
            if self.current_leader == node.unique_id or node.node_stats.state != 'Running':
                continue

            for leader_id in node.get_leaders():
                node.delete_leader(leader_id)

    def telegram_updates_handler(self):
        updates = self.telegram.get_updates()

        if not updates:
            return

        if 'restart' in updates['message']['text'].lower():
            node = [int(s) for s in updates['message']['text'].split() if s.isdigit()][0]
            if node > self.conf.number_of_nodes - 1:
                self.telegram.send_message(f'No nodes with that number')
                return
            self.restart_node(self.nodes[node].unique_id)

        elif 'stats' in updates['message']['text'].lower():
            for node in self.nodes:
                if 'Bootstrapping' == node.node_stats.state:
                    self.telegram.send_message(f'Node: {node.unique_id}:\n'
                                               f'Uptime: {node.node_stats.uptime}\n'
                                               f'State: {node.node_stats.state}\n')
                elif 'Running' == node.node_stats.state:
                    self.telegram.send_message(f'Node: {node.unique_id}:\n'
                                               f'Uptime: {node.node_stats.uptime}\n'
                                               f'BlockHeight: {node.node_stats.lastBlockHeight}\n'
                                               f'Delta PT: {node.node_stats.lastBlockHeight - self.pooltool.pooltoolmax}\n'
                                               f"Slot: {node.node_stats.lastBlockDate.split('.')[1]}\n"
                                               f'Peers: {node.network_stats.number_of_connections}')
                else:
                    self.telegram.send_message(f'Node: {node.unique_id}:\n'
                                               f'State: {node.node_stats.state}\n')

    def telegram_notifier(self):
        # Notify if out of sync for more than 1000 sec
        for node in self.nodes:
            if int(time.time()) - node.timeSinceLastBlock > 1000 and node.lastTgNotified + 600 < int(time.time()):
                self.telegram.send_message(
                    f"Node {node.unique_id} has not been in sync for {round(int(time.time()) - node.timeSinceLastBlock)} seconds")
                node.lastTgNotified = int(time.time())

        # Notify if current stake has changed
        if not self.current_leader < 0:
            self.nodes[self.current_leader].update_stakepool(self.conf.pool_id)
            total_stake = self.nodes[self.current_leader].stakepool.total_stake

            if self.current_total_stake > total_stake:
                self.current_total_stake = total_stake
                self.telegram.send_message(f'Your total stake has been reduced to {self.current_total_stake:n} ADA')

            elif self.current_total_stake < total_stake:
                self.current_total_stake = total_stake
                self.telegram.send_message(f'Your total stake has increased to {self.current_total_stake:n} ADA')

    def stuck_check(self, line, node):
        if (b'stuck_notifier' or b'task panicked' or b'cannot schedule getting next block') in line:
            print(f'Restarting node {node.unique_id} with message; \n {line}')

            if self.conf.telegrambot_active:
                self.telegram.send_message(f'Node {node.unique_id} with message; \n {line}')

            self.restart_node(node.unique_id)

    def read_nodes_output(self):
        while True:
            for node in self.nodes:
                line = node.get_node_output()
                if self.conf.log_to_file:
                    node.write_log_file(line.decode('utf-8'))
                elif self.conf.stuck_check_active:
                    self.stuck_check(line, node)

    def start_thread_node_stats(self):
        threading.Timer(self.conf.UPDATE_NODES_INTERVAL, self.start_thread_node_stats).start()
        for node in self.nodes:
            node.update_node_stats()

    def start_thread_leaders_logs(self):
        threading.Timer(15, self.start_thread_leaders_logs).start()
        for node in self.nodes:
            node.update_leaders_logs()
        self.blocks_left_this_epoch = self.nodes[self.current_leader].leaders.pending

    def start_thread_network_stats(self):
        threading.Timer(60, self.start_thread_network_stats).start()
        for node in self.nodes:
            node.update_network_stats()

    def start_threads_nodes(self):
        self.start_thread_node_stats()
        self.start_thread_leaders_logs()
        self.start_thread_network_stats()

    def start_thread_printer(self):
        threading.Timer(self.conf.PRINT_UPDATE_INTERVAL, self.start_thread_printer).start()
        self.printer.pretty_print_node_stats(self.nodes, self.pooltool.pooltoolmax)
        self.printer.print_dash()
        self.printer.pretty_print_latency(self.nodes)
        self.printer.print_dash()
        self.printer.print_epoch_and_block_info(self.diff_epoch_end_seconds,
                                                self.nodes[self.current_leader].leaders.leaders_logs,
                                                self.is_in_transition,
                                                self.next_block_time, self.total_blocks_this_epoch,
                                                self.blocks_minted_this_epoch, self.blocks_left_this_epoch)

    def start_thread_blocks_minted(self):
        threading.Timer(60, self.start_thread_blocks_minted).start()
        self.update_blocks_minted()

    def start_thread_next_block_time(self):
        threading.Timer(1, self.start_thread_next_block_time).start()
        self.update_next_block_time()

    def start_thread_leader_election(self):
        threading.Timer(self.conf.LEADER_ELECTION_INTERVAL, self.start_thread_leader_election).start()
        self.leader_election()

    def start_thread_bootstrap_stuck_check(self):
        threading.Timer(self.conf.BOOTSTRAP_STUCK_CHECK, self.start_thread_bootstrap_stuck_check).start()
        self.bootstrap_stuck_check()

    def start_thread_send_my_tip(self):
        threading.Timer(self.conf.SEND_MY_TIP_INTERVAL, self.start_thread_send_my_tip).start()
        self.send_my_tip()

    def start_thread_check_transition(self):
        threading.Timer(self.conf.TRANSITION_CHECK_INTERVAL, self.start_thread_check_transition).start()
        self.check_transition()

    def start_thread_leaders_check(self):
        threading.Timer(self.conf.LEADERS_CHECK_INTERVAL, self.start_thread_leaders_check).start()
        self.leaders_check()

    def telegram_handler(self):
        while True:
            self.telegram_updates_handler()
            self.telegram_notifier()
            time.sleep(0.5)

    def start_thread_telegram_notifier(self):
        thread = threading.Thread(target=self.telegram_handler)
        thread.start()

    def run(self):
        self.start_nodes()

        self.start_thread_printer()
        self.start_threads_nodes()
        self.start_thread_blocks_minted()
        self.start_thread_next_block_time()
        self.start_thread_leader_election()
        self.start_thread_bootstrap_stuck_check()
        self.start_thread_check_transition()
        self.start_thread_leaders_check()
        if self.conf.send_tip:
            self.start_thread_send_my_tip()
        if self.conf.telegrambot_active:
            self.start_thread_telegram_notifier()

        print('Done loading all threads')
        # if self.conf.stuck_check_active or self.conf.log_to_file:
        #     self.read_nodes_output()

import hashlib

def main():
    jor_controller = JorController()
    jor_controller.run()


if __name__ == "__main__":
    main()
