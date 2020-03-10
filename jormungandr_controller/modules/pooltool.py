import urllib
import base64
import subprocess
import os

import requests


class Pooltool:
    def __init__(self, pool_id):
        self.url_tip = 'https://api.pooltool.io/v0/sharemytip'
        self.url_minted = f'https://pooltool.s3-us-west-2.amazonaws.com/8e4d2a3/pools/{pool_id}/livestats.json'
        self.url_stats = 'https://pooltool.s3-us-west-2.amazonaws.com/stats/stats.json'
        self.extra = 'cGxhdGZvcm09am9ybXVuZ2FuZHJfY29udHJvbGxlci5weQ=='
        self.pool_id = pool_id
        self.pooltoolmax = 0
        print('Pooltool initialized')

    def pooltool_livestats(self):
        try:
            r = requests.get(url=self.url_minted)
        except requests.exceptions.RequestException as e:
            return {}
        return r.json()

    def pooltool_stats(self):
        try:
            r = requests.get(url=self.url_stats)
        except requests.exceptions.RequestException as e:
            return {}
        return r.json()

    def pooltool_send_my_tip(self, user_id, genesis_hash, lastBlockHeight, lastBlockHash, block):
        if block == '':
            return

        PARAMS = {'poolid': self.pool_id, 'userid': user_id, 'genesispref': genesis_hash, 'mytip': lastBlockHeight,
                  'lasthash': lastBlockHash, 'lastpool': block[168:168 + 64], 'lastParent': block[104:104 + 64],
                  'lastSlot': f'0x{block[24:24 + 8]}', 'lastEpoch': f'0x{block[16:16 + 8]}'}

        platform = urllib.parse.urlencode({"platform": "jormungandr_controller.py"})

        try:
            # sending get request and saving the response as response object
            r = requests.get(url=self.url_tip + '?' + base64.b64decode(self.extra).decode("utf-8"), params=PARAMS)
        except requests.exceptions.RequestException as e:
            return

        # extracting data in json format
        data = r.json()
        if data['success'] and data['confidence']:
            self.pooltoolmax = int(data['pooltoolmax'])

    def pooltool_send_slots(self, rest_port, user_id, genesis):  # TODO: implement own function instead of using script
        # if os.path.isfile(f'secret/passphrase_{current_epoch - 1}'):
        #     with open(f'secret/passphrase_{current_epoch - 1}', 'r') as last_passphrase:
        #         previous_key = last_passphrase.read()
        # else:
        #     previous_key = ''
        # if os.path.isfile(f'secret/passphrase_{current_epoch}'):
        #     with open(f'secret/passphrase_{current_epoch}', 'r') as current_passphrase:
        #         previous_key = current_passphrase.read()
        # else:
        #     previous_key = ''
        subprocess.run(['./send_slots.sh', f'{rest_port}', f'{self.pool_id}', f'{user_id}', f'{genesis}'],
                       stderr=subprocess.STDOUT)
