import subprocess

import yaml


class Settings:

    def __init__(self):
        self.slot_duration = 0
        self.slots_per_epoch = 0

    def update_settings(self, jcli_call, ip_address, port):
        settings = self.jcli_settings(jcli_call, ip_address, port)
        self.slot_duration = int(settings['slotDuration'])
        self.slots_per_epoch = int(settings['slotsPerEpoch'])

    def jcli_settings(self, jcli_call, ip_address, port):
        try:
            output = yaml.safe_load(subprocess.check_output(
                [jcli_call, 'rest', 'v0', 'settings', 'get', '-h', f'http://{ip_address}:{int(port)}/api'],
                stderr=subprocess.STDOUT))
        except subprocess.CalledProcessError as e:
            return {}
        return output
