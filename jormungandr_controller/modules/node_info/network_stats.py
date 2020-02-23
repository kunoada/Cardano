import subprocess

import yaml


class NetworkStats:

    def __init__(self):
        self.number_of_connections = 0

    def update_number_of_connections(self, jcli_call, ip_address, port):
        network_stats = self.jcli_network_stats(jcli_call, ip_address, port)
        self.number_of_connections = len(network_stats)

    def jcli_network_stats(self, jcli_call, ip_address, port):
        try:
            output = yaml.safe_load(subprocess.check_output([jcli_call, 'rest', 'v0', 'network', 'stats', 'get', '-h',
                                                             f'http://{ip_address}:{int(port)}/api'],
                                                            stderr=subprocess.STDOUT).decode('utf-8'))
        except subprocess.CalledProcessError as e:
            return []
        return output
