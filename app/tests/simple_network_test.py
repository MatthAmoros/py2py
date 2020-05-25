import pytest
import time
from threading import Thread
from app.node import Node

@pytest.fixture(scope="session")
def master_node():
	""" Build basic node that will be use to execute tests """
	return Node()

@pytest.fixture(scope="session")
def build_nodes():
	""" Build basic network with 4 very close nodes """
	nodes = {}
	node_1 = Thread(target=create_and_run_node, args=('54e40401677e1acca22de8cc6739a734a2d9d0e3', 59001))
	node_2 = Thread(target=create_and_run_node, args=('54e40401677e1acca22de8cc6739a734a2d9d0e4', 59002))

	node_1.start()
	node_2.start()

	nodes[0] = ('54e40401677e1acca22de8cc6739a734a2d9d0e3', 59001, node_1)
	nodes[1] = ('54e40401677e1acca22de8cc6739a734a2d9d0e4', 59002, node_2)

	return nodes

def create_and_run_node(id, port):
	my_node = Node(node_id=id, port=port)
	my_node.run()

def test_ping(build_nodes, master_node):
	""" Ping them """
	for index in build_nodes:
		node = build_nodes[index]
		""" Send ping request """
		target_ip = '127.0.0.1'
		target_port = int(node[1])
		assert(master_node.ping(('', target_ip, target_port)) == 0)

def test_store(build_nodes, master_node):
	""" Store and retrieve key """
	target_node = build_nodes[0]
	dummy_value = 'toto'
	dummy_key = '54e40401677e1acca22de8cc6739a734a2d9d0ef'

	""" Store key/value pair on target node """
	master_node.send_store_request(target=target_node[0], key=dummy_key, value=dummy_value)
	time.sleep(0.2)

	""" Request previously stored key/value pair """
	master_node.send_find_value_request(target=target_node[0], key=dummy_key)
	time.sleep(0.2)

	""" The target node should have respond with a STORE request, meaning we stored value locally """
	assert master_node.has_in_local_store(dummy_key) == dummy_value

def pytest_sessionfinish(session, exitstatus, build_nodes, master_node):
	""" Kill threads """
	for index in build_nodes:
		thread = node[2]
		thread.abort()
