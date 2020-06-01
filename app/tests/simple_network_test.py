import pytest
import time
import json
import os
from ctypes import c_char_p
from multiprocessing import Process, Value, Array, Manager
from app.node import Node

NETWORK_PEERS_COUNT = 30
k_depth = 20

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


@pytest.fixture(scope="session")
def master():
	my_node = Node(node_id='', port=0)
	my_node.run_listener()
	yield my_node

	""" Shutdown master """
	my_node.save_properties()
	my_node.shutdown()

def create_and_run_node():
	manager = Manager()
	o_node_id = manager.Value(c_char_p, 'ID')
	o_node_port = manager.Value('i', 1)
	o_running = manager.Value('i', 1)

	p = Process(target=run_in_new_process, args=(o_node_id, o_node_port, o_running))
	p.start()
	return p, o_node_id, o_node_port, o_running

def run_in_new_process(o_node_id, o_node_port, o_running):
	my_node = Node(node_id='', port=0)
	my_node.run_listener()
	o_node_id.value = my_node.node['id']
	o_node_port.value = int(my_node.node['port'])

	while o_running.value == 1:
		time.sleep(0.1)

	my_node.shutdown()
	return 0

def test_ping(master, network):
	""" Ping them """
	for node in network:
		if node[2].is_alive():
			if node[0].value != 'ID':
				print("### Pinging node: " + str(node[0].value)  + ":" + str(node[1].value))
				""" Send ping request """
				target_ip = '127.0.0.1'
				target_port = int(node[1].value)
				master.ping(('', target_ip, target_port))
		else:
			print("Process for node " + str(node[0].value) + " is not running.")

	""" Some might not respond, but at least 10% should have """
	assert master.kbuckets.known_contacts_count() > NETWORK_PEERS_COUNT / 10

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

def flatten_kbucket(kbucket):
	all_node = list()
	for i in kbucket:
		for node in kbucket[i]:
			all_node.append(node)

	return all_node

def test_bootstrap(master, network):
	""" Bootstrap nodes """
	for node in network:
		if node[2].is_alive():
			if node[0].value != 'ID':
				print("### Bootstraping node: " + str(node[0].value)  + ":" + str(node[1].value))
				target_ip = '127.0.0.1'
				target_port = int(node[1].value)
				""" Send bootstrap information """
				master._send_bootstrap_information(sender='', message= 'ID|' + str(node[0].value))

def test_store_echo(master, network):
	""" Store a key/value close to master, it should be progated and reach master node """
	for node in network[:k_depth]:
		if node[2].is_alive():
			if node[0].value != 'ID':
				print("### Send STORE to node: " + str(node[0].value)  + ":" + str(node[1].value))
				master.send_store_request(target=str(node[0].value), key=master.node['id'], value='ECHO')

	assert master.store.get_value(master.node['id']) == 'ECHO'
