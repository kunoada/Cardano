import time
import datetime

import tabulate


class Printer:
    def __init__(self):
        print('Printer initialized')

    def pretty_print_node_stats(self, nodes, pooltoolmax):
        headers = ['Node', 'State', 'Block height', 'pooltoolmax', 'Delta', 'Uptime', 'Time since last sync',
                   'Current leader']
        data = []

        for node in nodes:
            temp_list = []
            temp_list.extend(
                [f'Node {node.unique_id}', node.node_stats.state, node.node_stats.lastBlockHeight, pooltoolmax,
                 node.node_stats.lastBlockHeight - pooltoolmax, node.node_stats.uptime,
                 int(time.time()) - node.timeSinceLastBlock, node.is_leader])

            data.append(temp_list)

        print(tabulate.tabulate(data, headers))

    def print_dash(self):
        print('-')

    def pretty_print_latency(self, nodes):
        headers = ['Node', 'lastBlockTime', 'lastReceivedBlockTime', 'latency', 'avg5LastLatency', 'connections']
        data = []

        for node in nodes:
            temp_list = []
            temp_list.extend(
                [f'Node {node.unique_id}', node.node_stats.lastBlockTime, node.node_stats.lastReceivedBlockTime,
                 node.latency, node.avgLatencyRecords, node.network_stats.number_of_connections])
            data.append(temp_list)

        print(tabulate.tabulate(data, headers))

    def print_epoch_and_block_info(self, diff_epoch_end_seconds, leaders_logs, is_in_transition, next_block_time,
                                   total_blocks_this_epoch, blocks_minted_this_epoch, blocks_left_this_epoch):
        print(f'Time to next epoch: {str(datetime.timedelta(seconds=round(diff_epoch_end_seconds)))}')

        if is_in_transition:
            print('All nodes are currently leaders while no nodes has been elected for block creation')
        elif not leaders_logs:
            print('No blocks this epoch')
        else:
            if next_block_time == 0:
                print('No more blocks this epoch')
            else:
                print(
                    f"Time to your next block: {str(datetime.timedelta(seconds=round(next_block_time - int(time.time()))))}")
        print(f"Number of total blocks this epoch: {total_blocks_this_epoch}")
        print(f'Number of minted blocks this epoch: {blocks_minted_this_epoch}')
        print(f"Number of blocks left this epoch: {blocks_left_this_epoch}")
