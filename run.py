from node import Node
import socket
import sys

if len(sys.argv) > 1:
	command = sys.argv[1]

	if command == 'who':
		""" Get node id corresponding to ip/port """
		my_node = Node()
		target_ip = sys.argv[2]
		target_port = int(sys.argv[3])
		my_node.send_presentation_request((target_ip, target_port))
	elif command == 'ping':
		""" Send ping request """
		my_node = Node()
		target_ip = sys.argv[2]
		target_port = int(sys.argv[3])
		if my_node.ping(('', target_ip, target_port)) == 0:
			print("Online")
		else:
			print("Offline")
	elif command == 'get':
		""" Get topic """
		my_node = Node()
		my_node.get_topic(sys.argv[2])
		""" Run node and wait for response """
		my_node.run()
	elif command == 'init':
		""" Pass full path to a kbuckets.json file """
		my_node = Node()
		my_node.run(sys.argv[2])
else:
	my_node = Node()
	my_node.run()
