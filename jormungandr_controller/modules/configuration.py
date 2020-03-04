import json
import sys
import os.path


def validate_file_exist(path):
    if os.path.isfile(path):
        return True
    else:
        print(f"{path} is not a valid file, please check the path you have given in the config file!")
        return False


class Config:

    def __init__(self):
        try:
            config = json.load(open('my_config.json', 'r'))
        except json.JSONDecodeError as jd:
            print("Invalid json format in config file!\n"
                  "Remember to remove all comments!\n"
                  "You can use; https://jsonlint.com/, to validate json")
            print(jd)
            sys.exit(1)

        # Base configs
        self.jcli_call_format = config['Configuration']['jcli_call_format']
        self.jormungandr_call_format = config['Configuration']['jormungandr_call_format']
        self.stakepool_config_path = config['Configuration']['stakepool_config_path']
        self.node_secret_path = config['Configuration']['node_secret_path']
        self.genesis_hash = config['Configuration']['genesis_hash']
        self.pool_id = config['Configuration']['pool_id']
        self.number_of_nodes = config['Configuration']['number_of_nodes']
        self.use_seperate_storage = config['Configuration']['use_seperate_storage']
        self.log_to_file = config['Configuration']['log_to_file']

        # Time intervals
        self.LEADER_ELECTION_INTERVAL = config['Intervals']['LEADER_ELECTION']
        self.PRINT_UPDATE_INTERVAL = config['Intervals']['PRINT_UPDATE']
        self.UPDATE_NODES_INTERVAL = config['Intervals']['UPDATE_NODES']
        self.BOOTSTRAP_STUCK_CHECK = config['Intervals']['BOOTSTRAP_STUCK_CHECK']
        self.LAST_SYNC_RESTART = config['Intervals']['LAST_SYNC_RESTART']
        self.SEND_MY_TIP_INTERVAL = config['Intervals']['SEND_MY_TIP']
        self.TRANSITION_CHECK_INTERVAL = config['Intervals']['TRANSITION_CHECK']
        self.LEADERS_CHECK_INTERVAL = config['Intervals']['LEADERS_CHECK']

        # Pooltool setup
        self.pooltool_active = config['PooltoolSetup']['activate']
        if self.pooltool_active:
            self.user_id = config['PooltoolSetup']['user_id']

        # Telegram Bot setup
        self.telegrambot_active = config['TelegramBot']['activate']
        if self.telegrambot_active:
            self.token = config['TelegramBot']['token']
            self.chat_id = config['TelegramBot']['chat_id']

        self.stuck_check_active = config['StuckCheck']['activate']

        if 'utc_diff' in config:
            self.utc_diff = config['utc_diff']
        else:
            self.utc_diff = 0

        self.validate_configurations()

        print('Loaded configurations')

    def validate_configurations(self):
        if not validate_file_exist(self.stakepool_config_path) or not validate_file_exist(self.node_secret_path):
            sys.exit(1)
