import subprocess
import time

import yaml


class NodeStats:

    def __init__(self):
        # Base information
        self.uptime = 0
        self.state = ''
        self.timeSinceLastBlock = int(time.time())
        self.lastBlockHeight = 0
        self.lastBlockHash = 0
        self.lastBlockDate = ''
        self.lastBlockTime = ''
        self.lastReceivedBlockTime = ''

    def update_node_stats(self, jcli_call, ip_address, port):
        node_stats = self.jcli_node_stats(jcli_call, ip_address, port)

        if not node_stats:
            self.state = 'Starting'
            return

        self.state = node_stats['state']

        if self.state == ('Bootstrapping' or 'PreparingBlock0'):
            return

        self.uptime = node_stats['uptime']
        self.lastBlockHeight = int(node_stats['lastBlockHeight'])
        self.lastBlockHash = node_stats['lastBlockHash']
        self.lastBlockDate = node_stats['lastBlockDate']
        self.lastBlockTime = node_stats['lastBlockTime']
        self.lastReceivedBlockTime = node_stats['lastReceivedBlockTime']

    def jcli_node_stats(self, jcli_call, ip_address, port):
        try:
            output = yaml.safe_load(subprocess.check_output([jcli_call, 'rest', 'v0', 'node', 'stats', 'get', '-h',
                                                             f'http://{ip_address}:{int(port)}/api'],
                                                            stderr=subprocess.STDOUT).decode('utf-8'))
        except subprocess.CalledProcessError as e:
            return {}
        return output
