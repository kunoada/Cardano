import subprocess

import yaml


class Stakepool:
    def __init__(self):
        self.total_stake = 0

    def update_stakepool(self, jcli_call, ip_address, port, pool_id):
        stakepool = self.jcli_stakepool(jcli_call, ip_address, port, pool_id)
        if not stakepool:
            return
        self.total_stake = round(int(stakepool['total_stake']) / 1000000)  # round up to ada

    def jcli_stakepool(self, jcli_call, ip_address, port, pool_id):
        try:
            output = yaml.safe_load(
                subprocess.check_output([jcli_call, 'rest', 'v0', 'stake-pool', 'get', pool_id, '-h',
                                         f'http://{ip_address}:{int(port)}/api']).decode('utf-8'))
        except subprocess.CalledProcessError as e:
            return []
        return output