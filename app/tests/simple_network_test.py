import pytest

from app.node import Node

@pytest.fixture(scope="session")
def build_clients():
	my_node_1 = Node()
	my_node_1.run()

	my_node_2 = Node()
	my_node_2.run()

	my_node_3 = Node()
	my_node_3.run()

	my_node_4 = Node()
	my_node_4.run()

	return my_node
