import json
import requests
import time
import urllib
import threading

from dbhelper import DBHelper

db = DBHelper()

TOKEN = open('token', 'r').read()
URL = "https://api.telegram.org/bot{}/".format(TOKEN)

current_epoch = 0


def get_url(url):
    try:
        response = requests.get(url)
    except requests.exceptions.RequestException as e:
        return ''
    content = response.content.decode("utf8")
    return content


def get_json_from_url(url):
    content = get_url(url)
    if content == '':
        return
    js = json.loads(content)
    return js


def get_updates(offset=None):
    url = URL + "getUpdates"
    if offset:
        url += "?offset={}".format(offset)
    js = get_json_from_url(url)
    return js


def get_last_update_id(updates):
    update_ids = []
    for update in updates["result"]:
        update_ids.append(int(update["update_id"]))
    return max(update_ids)


def handle_updates(updates):
    for update in updates["result"]:
        text = update["message"]["text"].upper()
        chat = update["message"]["chat"]["id"]
        tickers = db.get_tickers(chat)
        if text == "/DELETE":
            keyboard = build_keyboard(tickers)
            send_message("Select an item to delete", chat, keyboard)
        elif text == "/START":
            send_message("Welcome to your personal stakepool notifier!\n"
                         "Please enter a TICKER of the pool you want to follow\n"
                         "\n"
                         "Example: KUNO", chat)
        elif text.startswith("/"):
            continue
        elif 3 > len(text) or len(text) > 5:
            message = "A TICKER needs to be between 3-5 letters!"
            send_message(message, chat)
        elif text in tickers:
            db.delete_item(chat, text)
            tickers = db.get_tickers(chat)
            message = "List of pools you watch:\n\n" + "\n".join(tickers)
            send_message(message, chat)
        else:
            pool_id = get_pool_id_from_ticker_file(text)
            if pool_id == '':
                pool_id = get_pool_id_from_ticker_url(text)
            if pool_id == '':
                message = "This is not a valid TICKER!"
                send_message(message, chat)
                continue
            elif pool_id == 'error':
                message = "There was an error, please try again"
                send_message(message, chat)
                continue
            db.add_item(chat, text)
            data = update_livestats(pool_id)
            db.update_items(chat, text, pool_id, data[0], data[1])
            tickers = db.get_tickers(chat)
            message = "List of pools you watch:\n\n" + "\n".join(tickers)
            send_message(message, chat)


def get_last_chat_id_and_text(updates):
    num_updates = len(updates["result"])
    last_update = num_updates - 1
    text = updates["result"][last_update]["message"]["text"]
    chat_id = updates["result"][last_update]["message"]["chat"]["id"]
    return (text, chat_id)


def build_keyboard(items):
    keyboard = [[item] for item in items]
    reply_markup = {"keyboard":keyboard, "one_time_keyboard": True}
    return json.dumps(reply_markup)


def send_message(text, chat_id, reply_markup=None):
    text = urllib.parse.quote_plus(text)
    url = URL + "sendMessage?text={}&chat_id={}&parse_mode=Markdown".format(text, chat_id)
    if reply_markup:
        url += "&reply_markup={}".format(reply_markup)
    get_url(url)


def get_pool_id_from_ticker_file(ticker):
    with open('tickers.json', 'r') as ticker_file:
        tickers = json.load(ticker_file)
    for pool_id in tickers['tickers']:
        if tickers['tickers'][pool_id] == ticker:
            return pool_id
    return ''

def get_pool_id_from_ticker_url(ticker):
    url_pool_ids = 'https://pooltool.s3-us-west-2.amazonaws.com/8e4d2a3/tickers.json'
    try:
        r = requests.get(url_pool_ids)
    except requests.exceptions.RequestException as e:
        return 'error'
    data = r.json()
    for pool_id in data['tickers']:
        if data['tickers'][pool_id] == ticker:
            return pool_id
    return ''


def get_livestats(pool_id):
    url_livestats = f'https://pooltool.s3-us-west-2.amazonaws.com/8e4d2a3/pools/{pool_id}/livestats.json'
    try:
        r = requests.get(url_livestats)
    except requests.exceptions.RequestException as e:
        return ''
    data = r.json()
    return data


def update_livestats(pool_id):
    data = get_livestats(pool_id)
    if data == '':
        return (0, 0, 0)
    return (round(int(data['livestake'])/1000000), data['epochblocks'], data['lastBlockEpoch'])


def get_stats():
    url_stats = 'https://pooltool.s3-us-west-2.amazonaws.com/stats/stats.json'
    try:
        r = requests.get(url_stats)
    except requests.exceptions.RequestException as e:
        return ''
    data = r.json()
    return data


def get_current_epoch():
    data = get_stats()
    if data == '':
        return
    return data['currentepoch']


def check_delegation_changes(chat_id, ticker, delegations, new_delegations):
    if delegations != new_delegations:
        db.update_delegation(chat_id, ticker, new_delegations)
        if delegations > new_delegations:
            message = f'{ticker}\n Your delegations has decreased to: {new_delegations} ADA'
            send_message(message, chat_id)
        elif delegations < new_delegations:
            message = f'{ticker}\n Your delegations has increased to: {new_delegations} ADA'
            send_message(message, chat_id)


def check_blocks_minted(chat_id, ticker, blocks_minted, new_blocks_minted, new_last_block_epoch):
    if new_last_block_epoch == current_epoch:
        if new_blocks_minted > blocks_minted:
            db.update_blocks_minted(chat_id, ticker, new_blocks_minted)
            message = f'{ticker}\n New block minted! Total blocks minted this epoch: {new_blocks_minted}'
            send_message(message, chat_id)
    else:
        db.update_blocks_minted(chat_id, ticker, 0)


def handle_notifier():
    global current_epoch
    chat_ids = list(set(db.get_chat_ids()))

    epoch = get_current_epoch()
    if current_epoch < epoch:
        # TODO: End of epoch notify
        for chat_id in chat_ids:
            tickers = db.get_tickers(chat_id)
            for ticker in tickers:
                pool_id , delegations , blocks_minted = db.get_items(chat_id , ticker)
                message = f'{ticker}\n ' \
                          f'Epoch {current_epoch} stats:\n' \
                          f'\n' \
                          f'Live stake {delegations}' \
                          f'Blocks minted: {blocks_minted}\n'
                send_message(message , chat_id)
        current_epoch = epoch

    for chat_id in chat_ids:
        tickers = db.get_tickers(chat_id)
        for ticker in tickers:
            pool_id, delegations, blocks_minted = db.get_items(chat_id, ticker)
            new_delegations, new_blocks_minted, new_last_block_epoch = update_livestats(pool_id)
            if new_last_block_epoch == 0:
                continue
            check_delegation_changes(chat_id, ticker, delegations, new_delegations)
            check_blocks_minted(chat_id, ticker, blocks_minted, new_blocks_minted, new_last_block_epoch)


def start_telegram_update_handler():
    last_update_id = None
    while True:
        updates = get_updates(last_update_id)
        if updates is not None:
            if len(updates["result"]) > 0:
                last_update_id = get_last_update_id(updates) + 1
                handle_updates(updates)
        time.sleep(0.5)


def start_telegram_notifier():
    ## On start init..
    global current_epoch
    current_epoch = get_current_epoch()
    ##
    while True:
        handle_notifier()
        time.sleep(1*60)


def main():
    db.setup()
    updates_handler = threading.Thread(target=start_telegram_update_handler)
    notifier = threading.Thread(target=start_telegram_notifier)

    updates_handler.start()
    notifier.start()


if __name__ == '__main__':
    main()