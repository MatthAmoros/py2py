import json
import os
import socket
import select
import base64
import hashlib

""" Kbucket max length """
max_contact = 20

""" Try load node an context """
node_loaded = 0
kbucket_loaded = 0

discovery_port = 43666

kbucket = list()
node = {}

""" Load kbucket from file """
try:
	with open('data/kbucket.json') as kbucket_file:
		kbucket = json.load(kbucket_file)
		kbucket_loaded = 1
except:
	pass

""" Load node configuration from file """
try:
	with open('data/node.json') as node_file:
		node = json.load(node_file)
		node_loaded = 1
except:
	pass

""" Generate 160 bit ID and digest """
if node_loaded == 0:
	node['id'] = hashlib.sha1(os.urandom(20)).hexdigest()

port = 0

if 'port' in node:
	port = int(node['port'])

""" Initialize socket """
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
	s.bind(('0.0.0.0',port))
except socket.error as e:
	if e.errno == errno.EADDRINUSE:
		print("Port is already in use, getting random availabel port.")
		s.bind(('0.0.0.0',0))
	pass

""" Not blocking """
s.setblocking(0)

if port == 0:
	node['port'] = int(s.getsockname()[1])

""" Main entry point for message coming into UDP socket """
def handle_message(message, sender):
	""" Handle incomming message """
	""" First message should be "ID|XXXXXXXXXXXXXXXXXXXXX|AT|XXXXXX" """
	message = base64.b64decode(message).decode('ASCII')

	print("Received " + message + " from " + str(sender[0]))
	if 'ID' in message:
		register_sender(sender, message)
	if 'WHO' in message:
		send_presentation(sender)
	if 'PING' in message:
		send_pong(sender, message)

""" Return header or presentation message containing ID and UDP port """
def build_presentation():
	return "ID|" + str(node['id']) + "|AT|" + str(node['port'])

""" Respond to ping request """
def send_pong(target, message):
	ping_port = int(message.split('|')[-1])
	payload = build_presentation() + "|" + "PONG"
	print("Sending pong to " + str(target[0]) + ":" + str(ping_port))
	send_payload(payload, (target[0], ping_port))

""" Send payload converted to base64 """
def send_payload(payload, target):
	print("Sending " + str(payload) + " to " + str(target))
	encoded = base64.b64encode(bytes(payload, "ASCII"))
	with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
		sock.sendto(encoded, target)

""" Sending node information """
def send_presentation(target):
	presentation = build_presentation()
	send_payload(presentation, target)

""" Requesting node information """
def send_presentation_request(target):
	presentation_request = build_presentation() + "|" + "WHO"
	send_payload(presentation_request, target)

""" Handle incomming presentation message """
def process_message(message):
	properties = message.split('|')
	sender_id = ''
	sender_port = ''

	if properties[0] == "ID":
		sender_id = properties[1]

	if properties[2] == "AT":
		sender_port = properties[3]

	return sender_id, sender_port

def ping(node_info):
	""" Setup listenning socket for pong """
	listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
	listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	listener.bind(('0.0.0.0',0))

	""" Get binded port """
	listening_port = int(listener.getsockname()[1])
	""" Send ping request """
	payload = build_presentation() + "|" + "PING|" + str(listening_port)
	send_payload(payload, (node_info[1], int(node_info[2])))

	listener.setblocking(0)
	""" Check if there is a response """
	""" Let receiver 500ms to respond """
	try:
		result = select.select([listener],[],[], 0.5)
		message, sender = result[0][0].recvfrom(2048)
		message = base64.b64decode(message).decode('ASCII')
		""" Check that response comes from target """
		if sender[0] == node_info[1]:
			if "PONG" in message:
				return 0
	except socket.error as e:
		print(str(e))
		pass
	except IndexError as ei:
		""" Did not respond """
		pass
	""" Something went wrong """
	return -1

""" Check if contact exists and return index """
def conctact_exists(sender_info):
	index = 0
	for contact in kbucket:
		if contact[0] == sender_info[0]:
			return index
		index = index + 1

	return -1

def register_sender(sender, message):
	sender_id = ''
	sender_port = 0

	sender_id, sender_port = process_message(message)
	""" Add sender address and port """
	sender_info = (sender_id, sender[0], sender_port)

	""" Contact already exists """
	contact_index = conctact_exists(sender_info)
	if contact_index > -1:
		""" Delete it, it will be added at the end of the list during next step """
		del kbucket[contact_index]

	""" We have more thant max contact count """
	if len(kbucket) > max_contact:
		""" Try reach least """
		if ping(kbucket[-1]) == -1:
			del kbucket[-1]
			kbucket.append(sender_info)
		else:
			""" Nothing, contact list is full """
	else:
		kbucket.append(sender_info)

	print("New kbucket:")
	print(str(kbucket))
	""" Save kbucket on disk """
	with open('data/kbucket.json', 'w+') as kbucket_file:
		json.dump(kbucket, kbucket_file)

""" Save node on disk """
try:
	with open('data/node.json', 'w+') as node_file:
		json.dump(node, node_file)
except:
	print("Could not save node configuration")
	pass

def run():
	print("Running node on UDP port " + str(node['port']))
	while True:
		result = select.select([s],[],[])
		""" Receive on first and only listening socket """
		msg, sender = result[0][0].recvfrom(2048)
		handle_message(msg, sender)
