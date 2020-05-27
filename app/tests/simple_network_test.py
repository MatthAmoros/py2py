import pytest
import time
from threading import Thread
from app.node import Node

@pytest.fixture(scope="session")
def master_node():
	""" Build basic node that will be use to execute tests """
	return create_and_run_node(id='', port=0)

@pytest.fixture(scope="session")
def network():
	""" Build basic network with 20 nodes """
	nodes = list()

	for i in range(0, 3):
		nodes.append(create_and_run_node('', 0))

	return nodes

def create_and_run_node(id, port):
	my_node = Node(node_id=id, port=port)
	my_node.run_listener()
	return my_node

def test_ping(network, master_node):
	""" Ping them """
	for node in network:
		""" Send ping request """
		target_ip = '127.0.0.1'
		target_port = int(node.node['port'])
		master_node.ping(('', target_ip, target_port))

	assert False
