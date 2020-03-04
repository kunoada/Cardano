import telegram


class TelegramBot:
    def __init__(self, token='', chat_id=''):
        self.token = token
        self.chat_id = chat_id
        self.bot = telegram.Bot(token=token)

        self.last_message_update_id = 0
        print('Telegram bot initialized')

    def get_updates(self):
        updates = self.bot.get_updates(offset=self.last_message_update_id + 1, timeout=100)
        if not updates:
            return {}
        last_message_received = updates[len(updates) - 1]  # Read only newest message
        self.last_message_update_id = last_message_received['update_id']
        return last_message_received

    def send_message(self, message):
        self.bot.sendMessage(chat_id=self.chat_id, text=message)
