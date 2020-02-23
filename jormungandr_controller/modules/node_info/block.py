import subprocess

import yaml


class Block:
    def __init__(self):
        self.block = ''

    def update_block(self, jcli_call, ip_address, port, lastBlockHash):
        self.block = self.jcli_block(jcli_call, ip_address, port, lastBlockHash)

    def jcli_block(self, jcli_call, ip_address, port, lastBlockHash):
        try:
            block = yaml.safe_load(subprocess.check_output(
                [jcli_call, 'rest', 'v0', 'block', lastBlockHash, 'get', '-h',
                 f'http://{ip_address}:{int(port)}/api']).decode('utf-8'))
            return block
        except subprocess.CalledProcessError as e:
            return ''
