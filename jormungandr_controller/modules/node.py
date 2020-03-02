import time
import collections
import subprocess
import datetime
import re

from modules.node_info.leaders import Leaders
from modules.node_info.network_stats import NetworkStats
from modules.node_info.node_stats import NodeStats
from modules.node_info.settings import Settings
from modules.node_info.block import Block
from modules.node_info.stakepool import Stakepool

import yaml


class Node:

    def __init__(self, unique_id, jcli_call, jor_call, genesis_hash, config_path, secret_path):
        self.unique_id = unique_id

        self.process_id = subprocess.Popen(
            [jor_call, '--genesis-block-hash', genesis_hash, '--config', config_path, '--secret', secret_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        # stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT) # Use this to just supress all output from node
        self.leaders = Leaders()
        self.network_stats = NetworkStats()
        self.node_stats = NodeStats()
        self.settings = Settings()
        self.block = Block()
        self.stakepool = Stakepool()

        self.ip_address, self.port = yaml.safe_load(open(config_path, 'r'))['rest']['listen'].split(':')
        self.jcli_call = jcli_call

        self.lastTgNotified = time.time()
        self.timeSinceLastBlock = int(time.time())
        self.current_blockHeight = 0
        self.latency = 10000
        self.last5LatencyRecords = collections.deque(maxlen=5)
        self.avgLatencyRecords = 10000
        self.is_leader = 1

        try:
            self.log_file = open(f'log_{self.unique_id}', 'w')
        except IOError as e:
            print('Could not open file: ' + e)

    def update_network_stats(self):
        self.network_stats.update_number_of_connections(self.jcli_call, self.ip_address, self.port)

    def update_leaders_logs(self):
        self.leaders.update_leaders_logs(self.jcli_call, self.ip_address, self.port)

    def update_node_stats(self):
        self.node_stats.update_node_stats(self.jcli_call, self.ip_address, self.port)

        if self.current_blockHeight < self.node_stats.lastBlockHeight:
            self.current_blockHeight = self.node_stats.lastBlockHeight
            self.timeSinceLastBlock = int(time.time())

            if self.node_stats.lastReceivedBlockTime is not None and self.node_stats.lastReceivedBlockTime != '':
                self.latency = time_between(
                    re.sub(r"([\+-]\d\d):(\d\d)(?::(\d\d(?:.\d+)?))?", r"\1\2\3", self.node_stats.lastBlockTime),
                    re.sub(r"([\+-]\d\d):(\d\d)(?::(\d\d(?:.\d+)?))?", r"\1\2\3",
                           self.node_stats.lastReceivedBlockTime))
                self.last5LatencyRecords.append(self.latency)

                if len(list(self.last5LatencyRecords)):
                    self.avgLatencyRecords = sum(list(self.last5LatencyRecords)) / len(list(self.last5LatencyRecords))

    def update_settings(self):
        self.settings.update_settings(self.jcli_call, self.ip_address, self.port)

    def update_stakepool(self, pool_id):
        self.stakepool.update_stakepool(self.jcli_call, self.ip_address, self.port, pool_id)

    def set_leader(self, node_secret_path):
        if not self.leaders.jcli_leader_post(self.jcli_call, self.ip_address, self.port, node_secret_path):
            return False
        self.is_leader = 1
        return True

    def delete_leader(self, id):
        if not self.leaders.jcli_leader_delete(self.jcli_call, self.ip_address, self.port, id):
            return False
        self.is_leader = 0
        return True

    def get_leaders(self):
        return self.leaders.jcli_leaders(self.jcli_call, self.ip_address, self.port)

    def get_block(self):
        self.block.update_block(self.jcli_call, self.ip_address, self.port, self.node_stats.lastBlockHash)
        return self.block.block

    def get_node_output(self):
        return self.process_id.stdout.readline()

    def shutdown_node(self):
        self.log_file.close()
        try:
            output = subprocess.check_output([self.jcli_call, 'rest', 'v0', 'shutdown', 'get', '-h',
                                              f'http://{self.ip_address}:{int(self.port)}/api']).decode('utf-8')
        except subprocess.CalledProcessError as e:
            return ''
        return output

    def write_log_file(self, message):
        if self.log_file.closed:
            return
        try:
            self.log_file.write(message)
            self.log_file.flush()
        except:
            print("Could not write to log file")



def time_between(d1, d2):
    d1 = datetime.datetime.strptime(d1, "%Y-%m-%dT%H:%M:%S%z")
    d2 = datetime.datetime.strptime(d2, "%Y-%m-%dT%H:%M:%S%z")
    return (d2 - d1).total_seconds()
