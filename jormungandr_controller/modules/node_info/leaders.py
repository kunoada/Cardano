import subprocess

import yaml


class Leaders:

    def __init__(self):
        self.leaders_logs = []
        self.pending = 0

    def update_leaders_logs(self, jcli_call, ip_address, port):
        self.leaders_logs = self.jcli_leaders_logs(jcli_call, ip_address, port)
        self.update_pending_leaders_logs()

    def update_pending_leaders_logs(self):
        pending = 0
        for log in self.leaders_logs:
            if 'Pending' in log['status']:
                pending += 1
        self.pending = pending

    def jcli_leaders_logs(self, jcli_call, ip_address, port):
        try:
            output = yaml.safe_load(subprocess.check_output([jcli_call, 'rest', 'v0', 'leaders', 'logs', 'get', '-h',
                                                             f'http://{ip_address}:{int(port)}/api'],
                                                            stderr=subprocess.STDOUT).decode('utf-8'))
        except subprocess.CalledProcessError as e:
            return []
        return output

    def jcli_leader_post(self, jcli_call, ip_address, port, node_secret_path):
        try:
            subprocess.run([jcli_call, 'rest', 'v0', 'leaders', 'post', '-f', node_secret_path, '-h',
                            f'http://{ip_address}:{int(port)}/api'])
            return True
        except subprocess.CalledProcessError as e:
            return False

    def jcli_leader_delete(self, jcli_call, ip_address, port, id):
        try:
            subprocess.run([jcli_call, 'rest', 'v0', 'leaders', 'delete', f'{id}', '-h',
                            f'http://{ip_address}:{int(port)}/api'])
            return True
        except subprocess.CalledProcessError as e:
            print("Could not delete old leader")
            return False

    def jcli_leaders(self, jcli_call, ip_address, port):
        try:
            output = yaml.safe_load(subprocess.check_output([jcli_call, 'rest', 'v0', 'leaders', 'get', '-h',
                                                             f'http://{ip_address}:{int(port)}/api']).decode('utf-8'))
            return output
        except subprocess.CalledProcessError as e:
            return []
