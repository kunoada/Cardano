import urllib
import base64
import hashlib
import json
import os

import requests


class Pooltool:
    def __init__(self, pool_id):
        self.url_tip = 'https://api.pooltool.io/v0/sharemytip'
        self.url_minted = f'https://pooltool.s3-us-west-2.amazonaws.com/8e4d2a3/pools/{pool_id}/livestats.json'
        self.url_stats = 'https://pooltool.s3-us-west-2.amazonaws.com/stats/stats.json'
        self.url_slots = 'https://api.pooltool.io/v0/sendlogs'
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

    def pooltool_send_slots(self, epoch_slots, current_epoch, user_id, genesis):
        with open(f'{current_epoch}_send_slot_logs', 'w') as f:

            if not os.path.isdir('leaders_logs'):
                os.makedirs('leaders_logs')

            if os.path.isfile(f'leaders_logs/leader_slots_{current_epoch - 1}'):
                with open(f'leaders_logs/leader_slots_{current_epoch - 1}', 'r') as last_slots:
                    previous_slots = last_slots.read()
            else:
                previous_slots = ''

            f.write("Writing leaders logs\n")
            if not os.path.isfile(f'leaders_logs/leader_slots_{current_epoch}'):
                with open(f'leaders_logs/leader_slots_{current_epoch}', 'w') as current_slots:
                    current_slots.write(json.dumps(epoch_slots))

            f.write("generating hash for leaders logs\n")
            current_hash = hashlib.sha256(json.dumps(epoch_slots).encode('utf-8')).hexdigest()
            f.write(f"current hash: {current_hash}\n")
            assigned = len(epoch_slots)
            f.write(f"assigned: {assigned}\n")

            PARAMS = {'currentepoch': current_epoch, 'poolid': self.pool_id, 'genesispref': genesis, 'userid': user_id,
                      'assigned_slots': assigned, 'this_epoch_hash': current_hash, 'last_epoch_slots': previous_slots}

            f.write(f"sending following parameters to POOLTOOL: {json.dumps(PARAMS)}")
            try:
                # sending get request and saving the response as response object
                r = requests.post(url=self.url_slots, data=json.dumps(PARAMS))
                f.write(r.text)
            except requests.exceptions.RequestException as e:
                f.write('Something when wrong sending slots!')
                return 'Something when wrong sending slots!'

            return r.text
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
        # subprocess.run(['./send_slots.sh', f'{rest_port}', f'{self.pool_id}', f'{user_id}', f'{genesis}'],
        #                stderr=subprocess.STDOUT)

#  This section is used only for hash validation -
#     if 'this_epoch_hash' in data:
#         datatowrite['epoch_hash']=data['this_epoch_hash']
#         json.dump_s3(datatowrite,tablepref+"/pools/"+data['poolid']+"/byepoch/"+str(int(currentepoch))+"/epoch_hash.json")
#
#     if 'last_epoch_slots' in data and data['last_epoch_slots']!='':
#         try:
#             previousepoch = json.load_s3(tablepref+"/pools/"+data['poolid']+"/byepoch/"+str(int(currentepoch) - 1)+"/epoch_hash.json") # should be -1
#         except:
#             return return_failure("you provided raw last epoch slots, but we don't have a hash recorded for the last epoch.  If this is your first epoch of submissions then do not submit a last_epoch_slots or submit an empty string.")
#
#         json.dump_s3(data['last_epoch_slots'],tablepref+"/pools/"+data['poolid']+"/byepoch/"+str(int(currentepoch) - 1)+"/epoch_slots.json")
#         last_epoch_slots_hash = hashlib.sha256(data['last_epoch_slots'].encode('utf-8')).hexdigest()
#         if last_epoch_slots_hash!=previousepoch['epoch_hash']:
#             qlresponse = graphql_query(f'mutation UpdatePool{tablepref} {{updatePool{tablepref}(input:{{id: "{poolid}", epochSlots: " "}}) {{{updatepoolfields}}}}}')
#             return return_failure("The hash of your slots submitted is not the same as the hash you provided last epoch")
#         else:
#             try:
#                 previous_epoch_slots = json.loads(data['last_epoch_slots'])
#             except:
#                 return return_failure("We were unable to parse json slot data.  Is the JSON valid?")
#
#             if len(previous_epoch_slots)!=int(previousepoch['assigned_slots']):
#                 qlresponse = graphql_query(f'mutation UpdatePool{tablepref} {{updatePool{tablepref}(input:{{id: "{poolid}", epochSlots: " "}}) {{{updatepoolfields}}}}}')
#                 return return_failure("You submitted assigned slots: " + str(previousepoch['assigned_slots']) +" But your hash verified leader logs contain: " + str(len(data['last_epoch_slots']))+" entries.  We have written your decoded leader logs to: " + tablepref + "/pools/"+data['poolid']+"/byepoch/"+str(int(currentepoch) - 1)+"/epoch_slots.json")
#
#             else:
#                 successData['previous_epoch_slots_verified']=True