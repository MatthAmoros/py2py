import pytest
import time
import json
import os
from ctypes import c_char_p
from multiprocessing import Process, Value, Array, Manager
from unittest.mock import MagicMock

from app.node import Node
from app.config import min_contact

NETWORK_PEERS_COUNT = 100
k_depth = 10
current_node_port = 32000

""" Spawn a network of nodes """
@pytest.fixture(scope="session")
def network():
	""" Build basic network with X nodes """
	nodes = list()

	for i in range(0, NETWORK_PEERS_COUNT):
		p, node_id, node_port, flag = create_and_run_node()
		nodes.append((node_id, node_port, p, flag))
	yield nodes

	""" Shutdown every node on the network """
	for node in nodes:
		if node[2].is_alive():
			node[3].value = 0

	still_alive = 0
	for node in nodes:
		node[2].join(1)
		if node[2].is_alive():
			still_alive = still_alive + 1

""" Returns master node """
@pytest.fixture(scope="session")
def master():
	my_node = Node(node_id='', port=current_node_port)
	node_port = current_node_port + 1
	my_node.run_listener()
	yield my_node

	""" Assert that we found tracked id or request expired """
	assert len(my_node.tracker.requests_queue) == 0
	""" Shutdown """
	my_node.save_properties()
	my_node.shutdown()

""" Spawn a new node in a separated process """
def create_and_run_node():
	manager = Manager()
	o_node_id = manager.Value(c_char_p, 'ID')
	o_node_port = manager.Value('i', 1)
	o_running = manager.Value('i', 1)

	p = Process(target=run_node_loop, args=(o_node_id, o_node_port, o_running))
	p.start()
	return p, o_node_id, o_node_port, o_running

""" Main node loop """
def run_node_loop(o_node_id, o_node_port, o_running):
	my_node = Node(node_id='', port=0)
	my_node.run_listener()
	o_node_id.value = my_node.node['id']
	o_node_port.value = int(my_node.node['port'])

	while o_running.value == 1:
		time.sleep(0.1)

	my_node.save_properties()
	my_node.shutdown()
	return 0

""" Send ping to each node of the network from master node """
""" At the end, master should have the knowledge of a minimum of contacts """
def test_ping(master, network):
	""" Ping them """
	for node in network[:k_depth]:
		if node[2].is_alive():
			if node[0].value != 'ID':
				print("### Pinging node: " + str(node[0].value)  + ":" + str(node[1].value))
				""" Send ping request """
				target_ip = '127.0.0.1'
				target_port = int(node[1].value)
				master.ping(('', target_ip, target_port))
		else:
			print("Process for node " + str(node[0].value) + " is not running.")

	""" We should have collected a minimum of contact info """
	assert master.kbuckets.known_contacts_count() >= min_contact \
	or master.kbuckets.known_contacts_count() >= k_depth

""" Return kbucket content """
def read_kbucket(node_id):
	structure = {}
	filepath = os.path.dirname(__file__) + '/../../data/' + node_id + '/kbuckets.json'

	try:
		with open(filepath) as kbuckets_file:
			structure = json.load(kbuckets_file)
	except Exception as e:
		print(e)
		pass

	return structure

""" Flatten kbucket to node list """
def flatten_kbucket(kbucket):
	all_node = list()
	for i in kbucket:
		for node in kbucket[i]:
			all_node.append(node)

	return all_node


""" Send bootstrap to every node of the network """
def test_bootstrap(master, network):
	""" Bootstrap nodes """
	for node in network[:k_depth]:
		if node[2].is_alive():
			if node[0].value != 'ID':
				print("### Bootstraping node: " + str(node[0].value)  + ":" + str(node[1].value))
				target_ip = '127.0.0.1'
				target_port = int(node[1].value)
				""" Send bootstrap information """
				master._send_bootstrap_information(sender='', message= 'ID|' + str(node[0].value))

""" Send a store request with master node ID as key """
""" Expected result is that the network should the store request back to master node as it's the closest node to this key (it's own ID) """
def test_store_echo(master, network):
	""" Store a key/value close to master, it should be progated and reach master node """
	for node in network[:k_depth]:
		if node[2].is_alive():
			if node[0].value != 'ID':
				print("### Send STORE to node: " + str(node[0].value)  + ":" + str(node[1].value))
				master.store(target=str(node[0].value), key=master.node['id'], value='ECHO')

	assert master._store.get_value(master.node['id']) == 'ECHO'

""" Find the first unknown node for master ID by querying its peers """
""" Expected result is that master ID should have knowledge of the node """
def test_find_node(master, network):
	searched_node_id = 'ffffffff'
	""" Looking for first unknown node of the network """
	for node in network[:k_depth]:
		if node[2].is_alive():
			if not master.kbuckets.is_known_id(node[0].value):
				searched_node_id = node[0].value
				master.store_key_pair(key=searched_node_id, value='searched_node_id')
				break
	print("### Looking for " + str(searched_node_id))
	""" Define callback to handle search result output """
	callback = MagicMock(return_value=3)
	def print_input(**kwargs):
		print(str(kwargs))
	callback.side_effect = print_input()

	master.find_node(node_id=searched_node_id, callback=callback)

	""" We have a tracker running for this request, or we found results """
	assert len(master.tracker.requests_queue) == 1 \
	or callback.called \
	or master.kbuckets.is_known_id(searched_node_id)
