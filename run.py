import node
import socket
import sys

if len(sys.argv) > 1:
	command = sys.argv[1]

	if command == 'who':
		""" Get node id corresponding to ip/port """
		target_ip = sys.argv[2]
		target_port = int(sys.argv[3])
		node.send_presentation_request((target_ip, target_port))
	elif command == 'ping':
		""" Send ping request """
		target_ip = sys.argv[2]
		target_port = int(sys.argv[3])
		if node.ping(('', target_ip, target_port)) == 0:
			print("Online")
		else:
			print("Offline")
	elif command == 'get':
		""" Get topic """
		node.get_topic(sys.argv[2])
		""" Run node and wait for response """
		node.run()
	elif command == 'init':
		""" Pass full path to a kbuckets.json file """
		node.run(sys.argv[2])
else:
	node.run()
