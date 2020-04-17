import node
import socket
import sys

if len(sys.argv) > 1:
	command = sys.argv[1]
	target_ip = sys.argv[2]
	target_port = int(sys.argv[3])
	if command == 'who':
		node.send_presentation_request((target_ip, target_port))
	elif command == 'ping':
		if node.ping(('', target_ip, target_port)) == 0:
			print("Online")
		else:
			print("Offline")
else:
	node.run()
