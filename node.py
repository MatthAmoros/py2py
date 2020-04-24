import json
import os
import errno
import socket
import select
import base64
import hashlib
import itertools
from data.config import id_length, group_prefix, max_contact, min_contact


class Node:
	""" Try load node and context """
	node_loaded = 0
	kbuckets_loaded = 0
	socket = None

	kbuckets = {}
	node = {}

	def __init__(self):
		""" Load node configuration from file """
		try:
			with open('data/node.json') as node_file:
				self.node = json.load(node_file)
				self.node_loaded = 1
		except:
			pass

		""" Generate bit ID and digest """
		if self.node_loaded == 0:
			self.node['id'] = os.urandom(id_length).hex()

		port = 0

		if 'port' in self.node:
			port = int(self.node['port'])

		""" Initialize socket """
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

		try:
			self.socket.bind(('0.0.0.0',port))
		except socket.error as e:
			if e.errno == errno.EADDRINUSE:
				print("Port is already in use, getting random available port.")
				self.socket.bind(('0.0.0.0',0))
			pass

		""" Not blocking """
		self.socket.setblocking(0)

		if port == 0:
			self.node['port'] = int(self.socket.getsockname()[1])

	def load_kbuckets(self, filepath):
		""" Load kbuckets from file """
		try:
			with open(filepath) as kbuckets_file:
				self.kbuckets = json.load(kbuckets_file)
				kbuckets_loaded = 1
		except:
			""" Init empty kbuckets """
			for distance in range(0, id_length*8 + 1):
				self.kbuckets[distance] = list()
			pass

		print("Kbuckets loaded: " + str(self.kbuckets))

	""" Main entry point for message coming into UDP socket """
	def handle_message(self, message, sender):
		""" Handle incomming message """
		""" Message header should be "ID|XXXXXXXXXXXXXXXXXXXXX|AT|XXXXXX" """
		message = base64.b64decode(message).decode('ASCII')
		print("Received " + message + " from " + str(sender[0]))
		if 'ID' in message:
			self.register_sender(sender, message)
		if 'WHO' in message:
			self.send_presentation(sender)
		if 'PING' in message:
			self.send_pong(sender, message)
		if 'GET' in message:
			""" GET|XXXXXX|FOR|XXXXXX """
			self.send_topic(sender, message)
		if 'TOP' in message:
			""" Found """
			self.handle_topic_found(sender, message)
		if 'NOP' in message:
			""" Not found """
			print("Not found: " + message)

	def handle_topic_found(self, sender, message):
		if 'FOR' in message:
			destination_node_id = message.split('|')[-1]
			""" Check that it's for us """
			if destination_node_id == node['id']:
				print("Found: " + message)
			else:
				""" Forward """
				self.send_payload(message, destination_node_id)

	def topiquify(searched_item):
		return searched_item

	def get_topic(self, topic):
		payload = self.build_presentation() + "|GET|" + str(topic) + "|FOR|" + self.node['id']
		""" Send to ourself """
		self.send_topic(('127.0.0.1', self.node['port']), payload)

	""" Lookup topic and send response """
	""" If topic is found in known object, return response to original sender """
	""" Else, forward to closest node """
	def send_topic(self, sender, message):
		payload = self.build_presentation()
		node_origin = message.split('|')[-1]
		topic = message.split('|')[-3]
		closest_node = self.get_closest_known_node(topic)

		if 	closest_node is None:
			print("Nothing found.")
		elif closest_node[0] == self.node['id'] and topic != self.node['id']:
			""" We are the closest, and we didn't found topic """
			""" Send not found """
			payload = payload + "|NOP|" + closest_node[1] + ":" + closest_node[2]
			self.send_payload(payload, node_origin)
		elif len(closest_node) == 3:
			if closest_node[0] == topic:
				""" We found requested node, send contact information """
				payload = payload + "|TOP|" + closest_node[1] + ":" + closest_node[2]
				print("Found, send response to original sender")
				self.send_payload(payload, node_origin)
			else:
				""" Didn't found requested node, forward to closest """
				payload = self.build_presentation() + "|GET|" + topic + "|FOR|" + node_origin
				print("Topic not known, sending to closest: " + str(closest_node))
				self.send_payload(payload, (closest_node[1], int(closest_node[2])))
		else:
			print("Not connected to py2py network.")

	""" Return header or presentation message containing ID and UDP port """
	def build_presentation(self):
		return "ID|" + str(self.node['id']) + "|AT|" + str(self.node['port'])

	""" Respond to ping request """
	def send_pong(self, target, message):
		ping_port = int(message.split('|')[-1])
		payload = self.build_presentation() + "|" + "PONG"
		print("Sending pong to " + str(target[0]) + ":" + str(ping_port))
		self.send_payload(payload=payload, target=(target[0], int(ping_port)))

	""" Send payload converted to base64 """
	def send_payload(self, payload, target):
		encoded = base64.b64encode(bytes(payload, "ASCII"))

		""" If target is node Id, get corresponding node or closest """
		if isinstance(target, str):
			if target == self.node['id']:
				target = ('127.0.0.1', int(self.node['port']))
			else:
				closest_node = self.get_closest_known_node(target)
				""" Extract IP / Port """
				print("Node not known, sending to closest: " + str(closest_node))
				target = (closest_node[1], int(closest_node[2]))

		with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
			sock.sendto(encoded, target)
		print("Sending " + str(payload) + " to " + str(target))

	""" Sending node information """
	def send_presentation(self, target):
		presentation = self.build_presentation()
		self.send_payload(presentation, target)

	""" Requesting node information """
	def send_presentation_request(self, target):
		presentation_request = self.build_presentation() + "|" + "WHO"
		self.send_payload(presentation_request, target)

	""" Handle incomming presentation message """
	def process_message(self, message):
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
	def distance_from_me(self, target_id):
		return compute_distance(self.node['id'], target_id)

	""" Flatten kbuckets """
	def get_all_known_nodes(self):
		all_node = list()
		for i in self.kbuckets:
			for node in self.kbuckets[i]:
				all_node.append(node)

		return all_node

	""" Get closest node to target node id """
	""" Returns full node description (id, ip, port) """
	def get_closest_known_node(self, target_id):
		""" Check if kbuckets exists """
		if len(self.kbuckets) == 0:
			default_path = 'data/' + self.node['id'] + '/kbuckets.json'
			self.load_kbuckets(default_path)

		distance = self.distance_from_me(target_id)
		""" Get corresponding bucket """
		if distance in self.kbuckets:
			kbucket = self.kbuckets[distance]
		else:
			""" Empty """
			kbucket = list()

		""" Init to max distance """
		min = id_length * 8
		closest_node = None

		if len(kbucket) > 0:
			for _node in kbucket:
				tmp = compute_distance(_node[0], target_id)
				if tmp < min:
					min = tmp
					closest_node = _node
		else:
			""" Check for closest node, without filtering bucket """
			all_nodes = self.get_all_known_nodes()
			for _node in all_nodes:
				tmp = compute_distance(_node[0], target_id)
				print("Node " + str(_node[0]) + " distance " + str(tmp) + " min " + str(min))
				if tmp < min:
					min = tmp
					closest_node = _node

		return closest_node

	""" Try reach node, timeout 500 ms """
	""" Returns 0 on success """
	def ping(self, node_info):
		""" Setup listenning socket for pong """
		listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
		listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		listener.bind(('0.0.0.0',0))

		""" Get binded port """
		listening_port = int(listener.getsockname()[1])
		""" Send ping request """
		payload = self.build_presentation() + "|" + "PING|" + str(listening_port)
		self.send_payload(payload, (node_info[1], int(node_info[2])))

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
					self.register_sender(sender, message)
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
	def conctact_exists(self, sender_info, distance):
		index = 0
		kbucket = self.kbuckets[distance]
		for contact in kbucket:
			if contact[0] == sender_info[0]:
				return index
			index = index + 1

		return -1

	""" Register sender in corresponding kbucket """
	def register_sender(self, sender, message):
		sender_id = ''
		sender_port = 0

		sender_id, sender_port = self.process_message(message)
		""" Add sender address and port """
		sender_info = (sender_id, sender[0], sender_port)
		""" Compute distance between nodes (XOR) """
		distance = self.distance_from_me(sender_id)
		contact_limit = get_max_bucket_peers(distance)

		if distance > 0:
			if distance not in self.kbuckets:
				self.kbuckets[distance] = list()

			""" Contact already exists """
			contact_index = self.conctact_exists(sender_info, distance)
			if contact_index > -1:
				""" Delete it, it will be added at the end of the list during next step """
				del self.kbuckets[distance][contact_index]

			""" We have more than max contact count """
			if len(self.kbuckets[distance]) >= contact_limit:
				""" Try reach least seen (first one) """
				if ping(self.kbuckets[distance][0]) == -1:
					del self.kbuckets[distance][0]
					self.kbuckets[distance].append(sender_info)
				else:
					""" Nothing, contact list is full """
			else:
				self.kbuckets[distance].append(sender_info)

			""" Save kbuckets on disk """
			filename = 'data/' + self.node['id'] + '/kbuckets.json'
			os.makedirs(os.path.dirname(filename), exist_ok=True)
			with open(filename, 'w+') as kbuckets_file:
				json.dump(self.kbuckets, kbuckets_file)

	def run(self, kbuckets_full_path=''):
		must_shutdown = False
		if len(kbuckets_full_path) > 0:
			self.load_kbuckets(kbuckets_full_path)
		else:
			default_path = 'data/' + self.node['id'] + '/kbuckets.json'
			self.load_kbuckets(default_path)

		print("Running node " + str(self.node['id']) + " on UDP port " + str(int(self.socket.getsockname()[1])))
		while not must_shutdown:
			try:
				result = select.select([self.socket],[],[])
				""" Receive on first and only listening socket """
				msg, sender = result[0][0].recvfrom(2048)
				self.handle_message(msg, sender)
			except KeyboardInterrupt:
				""" Clean shutdown """
				must_shutdown = True
				pass

		""" Save node on disk """
		try:
			filename = 'data/node.json'
			os.makedirs(os.path.dirname(filename), exist_ok=True)
			with open(filename, 'w+') as node_file:
				json.dump(self.node, node_file)
		except:
			print("Could not save node configuration")
			pass

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
