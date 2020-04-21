import json
import os
import errno
import socket
import select
import base64
import hashlib

"""
	Configuration
"""
""" Byte length """
id_length = 4
""" Node ID length correpsonding to prefix (used to compute distance) """
group_prefix = 10
""" kbuckets max length (peers count per bucket) """
max_contact = 20
""" kbuckets min length (peers count per bucket), used to maintain a minimum peers count for farther distance """
min_contact = 5

"""
	Actual code
"""
""" Try load node an context """
node_loaded = 0
kbuckets_loaded = 0

discovery_port = 43666

kbuckets = {}
node = {}

""" Load kbuckets from file """
try:
	with open('data/kbuckets.json') as kbuckets_file:
		kbuckets = json.load(kbuckets_file)
		kbuckets_loaded = 1
except:
	""" Init empty kbuckets """
	for distance in range(0, id_length*8 + 1):
		kbuckets[distance] = list()
	pass

""" Load node configuration from file """
try:
	with open('data/node.json') as node_file:
		node = json.load(node_file)
		node_loaded = 1
except:
	pass

""" Generate bit ID and digest """
if node_loaded == 0:
	node['id'] = os.urandom(id_length).hex()

port = 0

if 'port' in node:
	port = int(node['port'])

""" Initialize socket """
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

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
	""" Message header should be "ID|XXXXXXXXXXXXXXXXXXXXX|AT|XXXXXX" """
	message = base64.b64decode(message).decode('ASCII')
	print("Received " + message + " from " + str(sender[0]))
	if 'ID' in message:
		register_sender(sender, message)
	if 'WHO' in message:
		send_presentation(sender)
	if 'PING' in message:
		send_pong(sender, message)
	if 'GET' in message:
		""" GET|XXXXXX|FOR|XXXXXX """
		send_topic(sender, message)
	if 'TOP' in message:
		print("Topic found")

""" Lookup topic and send response """
""" If topic is found in known object, return response to original sender """
""" Else, forward to closest node """
def send_topic(sender, message):
	payload = build_presentation()
	node_origin = message.split('|')[-1]
	topic = message.split('|')[-3]
	closest_node = get_closest_known_node()

	if closest_node[0] == topic:
		""" We found requested node, send contact information """
		payload = payload + "|TOP|" + closest_node[1] + ":" + closest_node[2]
		send_payload(payload, node_origin)
	else:
		""" Didn't found requested node, forward to closest """
		payload = message
		send_payload(payload, (closest_node[1], closest_node[2]))

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
	encoded = base64.b64encode(bytes(payload, "ASCII"))

	""" If target is node Id, get corresponding node or closest """
	if isinstance(target, str):
		closest_node = get_closest_known_node(target)
		""" Extract IP / Port """
		target = (closest_node[1], closest_node[2])

	with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
		sock.sendto(encoded, target)
	print("Sending " + str(payload) + " to " + str(target))

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
	""" Static search for parameters """
	if properties[0] == "ID":
		sender_id = properties[1]

	if properties[2] == "AT":
		sender_port = properties[3]

	return sender_id, sender_port

""" Returns distance from current node """
def distance_from_me(target_id):
	return compute_distance(node['id'], target_id)

""" Flatten kbuckets """
def get_all_known_nodes():
	return [node for bucket in kbuckets for node in bucket]

""" Get closest node to target node id """
""" Returns full node description (id, ip, port) """
def get_closest_known_node(taget_id):
	distance = distance_from_me(taget_id)
	""" Get corresponding bucket """
	kbucket = kbuckets[distance]
	""" Init to max distance """
	min = id_length * 8
	closest_node = None

	if len(kbucket) > 0:
		for node in kbucket:
			tmp = compute_distance(node[0], target_id)
			if tmp < min:
				min = tmp
				closest_node = node
	else:
		""" Check for closest node, without filtering bucket """
		all_nodes = get_all_known_nodes()
		for node in all_nodes:
			tmp = compute_distance(node[0], target_id)
			if tmp < min:
				min = tmp
				closest_node = node

	return closest_node

""" Try reach node, timeout 500 ms """
""" Returns 0 on success """
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

""" Compute distance using integer XOR """
def compute_distance(node1_id, node2_id):
	int_node1 = int(node1_id, 16)
	int_node2 = int(node2_id, 16)
	int_distance = int_node1 ^ int_node2

	str_distance = "{0:b}".format(int_distance)
	""" If we don't have bit length, we pad """
	str_distance = str_distance.zfill(id_length * 8)

	common_prefix_length = 0

	for char in str_distance:
		if char == '0':
			common_prefix_length = common_prefix_length + 1
		else:
			break

	distance = (id_length * 8) - common_prefix_length
	return distance

""" Check if contact exists and return index """
def conctact_exists(sender_info, distance):
	index = 0
	kbucket = kbuckets[distance]
	for contact in kbucket:
		if contact[0] == sender_info[0]:
			return index
		index = index + 1

	return -1

""" Returns max contact per bucket according to distance """
def get_max_bucket_peers(distance):
	limit = max_contact

	""" Max bucket count is lenght of id in bit """
	max_buckets = id_length * 8

	""" For short distance we want to store more contact """
	limit = round(max_contact / max_buckets) * (max_buckets - distance)

	""" Avoid 0, always store at least one contact """
	if limit < min_contact:
		limit = min_contact

	return limit

""" Register sender in corresponding kbucket """
def register_sender(sender, message):
	sender_id = ''
	sender_port = 0

	sender_id, sender_port = process_message(message)
	""" Add sender address and port """
	sender_info = (sender_id, sender[0], sender_port)
	""" Compute distance between nodes (XOR) """
	distance = distance_from_me(sender_id)
	contact_limit = get_max_bucket_peers(distance)

	if distance > 0:
		if distance not in kbuckets:
			kbuckets[distance] = list()

		""" Contact already exists """
		contact_index = conctact_exists(sender_info, distance)
		if contact_index > -1:
			""" Delete it, it will be added at the end of the list during next step """
			del kbuckets[distance][contact_index]

		""" We have more than max contact count """
		if len(kbuckets[distance]) >= contact_limit:
			""" Try reach least seen (first one) """
			if ping(kbuckets[distance][0]) == -1:
				del kbuckets[distance][0]
				kbuckets[distance].append(sender_info)
			else:
				""" Nothing, contact list is full """
		else:
			kbuckets[distance].append(sender_info)

		""" Save kbuckets on disk """
		with open('data/kbuckets.json', 'w+') as kbuckets_file:
			json.dump(kbuckets, kbuckets_file)

""" Save node on disk """
try:
	with open('data/node.json', 'w+') as node_file:
		json.dump(node, node_file)
except:
	print("Could not save node configuration")
	pass

def run():
	print("Running node on UDP port " + str(int(s.getsockname()[1])))
	while True:
		result = select.select([s],[],[])
		""" Receive on first and only listening socket """
		msg, sender = result[0][0].recvfrom(2048)
		handle_message(msg, sender)
