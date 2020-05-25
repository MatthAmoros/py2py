#!/usr/bin/env python
#encoding: utf-8

import json
import os
import errno
import socket
import select
import base64
import hashlib
import itertools
from app.config import id_length, group_prefix, max_contact, min_contact, ip_address, answer_ping_behavior, interest_radius, verbose
from app.kbucket import Kbucket
from app.store import Store
from app.constants import *

class Node:
	""" Try load node and context """
	node_loaded = 0
	kbuckets_loaded = 0
	socket = None

	kbuckets = None
	node = {}
	store = None

	def __init__(self, node_id='', port=0):
		""" Load node configuration from file """
		if node_id == '':
			try:
				with open('data/node.json') as node_file:
					self.node = json.load(node_file)
					self.node_loaded = 1
			except:
				pass
		else:
			self.node['id'] = node_id
			self.node['port'] = port
			self.node_loaded = 1

		""" Generate bit ID and digest """
		if self.node_loaded == 0:
			self.node['id'] = generate_hash(str(os.urandom(id_length).hex()))

		port = 0

		if 'port' in self.node:
			port = int(self.node['port'])

		""" Initialize socket """
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

		try:
			self.socket.bind((ip_address,port))
		except socket.error as e:
			if e.errno == errno.EADDRINUSE:
				if verbose == 1:
					print("Port is already in use, getting random available port.")
				self.socket.bind((ip_address,0))
			pass

		""" Not blocking """
		self.socket.setblocking(0)

		if port == 0:
			self.node['port'] = int(self.socket.getsockname()[1])

		""" Initialize kbucket """
		self.kbuckets = Kbucket(node_id=self.node['id'], id_length=id_length)
		self.kbuckets.load_kbuckets()

		""" Initialize store """
		self.store = Store()

	""" Main entry point for message coming into UDP socket """
	def _handle_message(self, message, sender):
		""" Handle incomming message """
		""" Message header should be "ID|XXXXXXXXXXXXXXXXXXXXX|AT|XXXXXX" """
		message = base64.b64decode(message).decode('ASCII')
		if verbose == 1:
			print("_handle_message:: Received " + message + " from " + str(sender[0]))

		if 'ID' in message:
			self.register_sender(sender, message)
		if 'PING' in message:
			self._send_pong(sender, message)
		if 'STORE' in message:
			""" Called to store a key/value pair or to answer FIND_VALUE request """
			""" STORE|KEY|VALUE """
			self._store_key_pair_message(sender, message)
		if 'FIND_NODE' in message:
			""" Get topic """
			""" FIND_NODE|XXXXXX|FOR|XXXXXX """
			self._send_topic(sender=sender, message=message)
		if 'FIND_VALUE' in message:
			""" Get topic """
			""" FIND_VALUE|XXXXXX|FOR|XXXXXX """
			self._send_key_value_response(sender, message)

		if 'NOP' in message:
			""" Not found """
			if verbose == 1:
				print(message)

	""" Order a node to store a key value pair """
	def send_store_request(self, target, key, value):
		store_request = self._build_presentation() + "|STORE|" + key + "|" + value
		self.send_payload(store_request, target)

	""" Store a key value pair from received message """
	def _store_key_pair_message(self, sender, message):
		store_request = self.strip_out_message_header(message)
		key, value = (store_request.split('|')[1], store_request.split('|')[2])
		self.store_key_pair(key=key, value=value)

	""" Store a key value pair """
	def store_key_pair(self, key, value):
		self.store.add_key_value(key, value)
		if verbose == 1:
			print("store_key_pair::add_key_value:: Stored [" + str(key) + "]:" + str(value) + " at node [" + self.node['id'] + "]")

	""" Check if key has an associated value in local storage """
	def has_in_local_store(self, key):
		return self.store.get_value(key)

	""" Send FIND_VALUE request """
	def send_find_value_request(self, target, key):
		find_value_request = self._build_presentation() + "|FIND_VALUE|" + key + "|FOR|" + self.node['id']
		self.send_payload(find_value_request, target)

	""" Send resposne to FIND_VALUE query """
	def _send_key_value_response(self, sender, message):
		key_value_request = self.strip_out_message_header(message)
		key, dest = (key_value_request.split('|')[1], key_value_request.split('|')[3])
		found_value = self.store.get_value(key)

		if len(found_value) > 0:
			""" Found """
			response_payload = self._build_presentation() + "|STORE|" + key + "|" + found_value
		else:
			""" Not found """
			response_payload = self._build_presentation() + "|NOP|" + key

		self.send_payload(response_payload, dest)

	def handle_forward(self, sender, message):
		if 'FOR' in message:
			destination_node_id = message.split('|')[-1]
			""" Check that it's for us """
			if destination_node_id == self.node['id']:
				""" Remove forward flag, resend to self """
				message = message.replace('|FOR|' + str(destination_node_id), '')
				if verbose == 1:
					print("handle_forward:: Is for me " + str(message))
				self.send_payload(message, self.node['id'])
			else:
				""" Forward """
				if verbose == 1:
					print("handle_forward:: Forward " + str(message))
				self.send_payload(message, destination_node_id)

	def send_find_node_request(self, topic):
		payload = self._build_presentation() + "|FIND_NODE|" + str(topic) + "|FOR|" + self.node['id']
		""" Send to ourself """
		self._send_topic(('127.0.0.1', self.node['port']), payload)

	def handle_topic_information(self, message):
		""" Handle topic information """
		sender_id, sender_port = self.process_message(message)
		""" Remove header """
		message = message.replace('ID|' + str(sender_id) + '|AT|' + str(sender_port) + '|', '')
		""" INFO|493b1310|AT|87f1640e """
		""" Extract topic_id """
		topic_id, sender_id = message.split('|')[1], message.split('|')[3]
		if self.kbuckets.is_of_interest(topic_id):
			payload = self._build_presentation() + "|FIND_NODE|" + str(topic_id) + "|FOR|" + self.node['id']
			self._send_topic(sender_id, payload)
		else:
			if verbose == 1:
				print("handle_topic_information:: Skipping, out of radius")

	def strip_out_message_header(self, message):
		id, port = self.process_message(message)
		return message.replace('ID|' + str(id) + '|AT|' + str(port) + '|', '')

	def inform_topic(self, topic_id):
		""" Inform network of a new available topic """
		""" Inform closest only """
		closest_node = self.kbuckets.get_closest_known_node(topic_id, allow_matching_exact=False)
		if closest_node is not None and self.not_self(closest_node) :
			self.send_inform_topic(closest_node[0], topic_id)
		else:
			if verbose == 1:
				print("inform_topic:: No nodes.")

	def send_inform_topic(self, target, topic_id):
		""" Send topic id """
		payload = self._build_presentation() + "|INFO|" + str(topic_id) + "|AT|" + self.node['id']
		self.send_payload(payload, target)

	""" Lookup topic and send response """
	""" If topic is found in known object, return response to original sender """
	""" Else, forward to closest node """
	def _send_topic(self, sender, message):
		payload = self._build_presentation()
		sender_id, _ = self.process_message(message)
		node_origin_id = message.split('|')[-1]
		topic = message.split('|')[-3]
		closest_node = self.kbuckets.get_closest_known_node(topic)

		if verbose == 1:
			print("_send_topic:: Looking for [" + str(topic) + "]")

		if closest_node is None:
			if verbose == 1:
				print("_send_topic:: Nothing found.")

			payload = payload + "|NOP|" + str(topic) + "|FOR|" + node_origin_id
			self.send_payload(payload, node_origin_id)
		elif closest_node[0] == self.node['id'] and topic != self.node['id']:
			""" We are the closest we know, and we didn't found topic """
			""" Send not found """
			payload = payload + "|NOP|" + str(topic) + "|FOR|" + node_origin_id
			self.send_payload(payload, node_origin_id)
		elif len(closest_node) == 3:
			if closest_node[0] == topic:
				""" We found requested node, send contact information """
				payload = payload + "|TOP|" + closest_node[1] + ":" + closest_node[2]  + "|FOR|" + node_origin_id

				if verbose == 1:
					print("_send_topic:: Found, send response to original sender")

				self.send_payload(payload, node_origin_id)
			elif closest_node[0] != node_origin_id and closest_node[0] != sender_id:
				""" Didn't found requested node, forward to closest that is not sender nor original sender """
				payload = self._build_presentation() + "|GET|" + topic + "|FOR|" + node_origin_id

				if verbose == 1:
					print("_send_topic:: Topic not known, sending to closest: " + str(closest_node))

				self.send_payload(payload, (closest_node[1], int(closest_node[2])))
			else:
				if verbose == 1:
					print("_send_topic:: Nothing found.")

				payload = payload + "|NOP|" + str(topic) + "|FOR|" + node_origin_id
				self.send_payload(payload, node_origin_id)
		elif len(closest_node) == 2:
			""" Data topic """
			payload = payload + "|TOP|" + closest_node[0] + "|" + closest_node[1] + "|FOR|" + node_origin_id

			if verbose == 1:
				print("_send_topic:: Found, data topic, send response to original sender")

			self.send_payload(payload, node_origin_id)
		else:
			if verbose == 1:
				print("_send_topic:: Not connected to py2py network.")

	""" Return header or presentation message containing ID and UDP port """
	def _build_presentation(self):
		return "ID|" + str(self.node['id']) + "|AT|" + str(self.node['port'])

	""" Respond to ping request """
	def _send_pong(self, target, message):
		if answer_ping_behavior == ANSWER_PING_ALWAYS \
		or answer_ping_behavior == ANSWER_PING_TRUSTED:
			if answer_ping_behavior == ANSWER_PING_TRUSTED:
				if self.is_trusted(target):
					ping_port = int(message.split('|')[-1])
					payload = self._build_presentation() + "|" + "PONG"
					print("_send_pong:: Sending pong to " + str(target[0]) + ":" + str(ping_port))
					self.send_payload(payload=payload, target=(target[0], int(ping_port)))
			else:
				ping_port = int(message.split('|')[-1])
				payload = self._build_presentation() + "|" + "PONG"
				print("_send_pong:: Sending pong to " + str(target[0]) + ":" + str(ping_port))
				self.send_payload(payload=payload, target=(target[0], int(ping_port)))

	def is_trusted(self, node):
		return False

	""" Send payload converted to base64 """
	def send_payload(self, payload, target):
		encoded = base64.b64encode(bytes(payload, "ASCII"))

		""" If target is node Id, get corresponding node or closest """
		if isinstance(target, str):
			if target == self.node['id']:
				target = ('127.0.0.1', int(self.node['port']))
			else:
				closest_node = self.kbuckets.get_closest_known_node(target)
				""" Node not found, sending to closest """
				if closest_node[0] != target:
					if verbose == 1:
						print("send_payload:: Node ID [" + target + "] not known, sending to closest: " + str(closest_node))
				""" Extract IP / Port """
				target = (closest_node[1], int(closest_node[2]))
		if verbose == 1:
			print("send_payload:: Sending [" + str(payload) + "] to: " + str(target))
		with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
			sock.sendto(encoded, target)

	""" Sending node information """
	def send_presentation(self, target):
		presentation = self._build_presentation()
		self.send_payload(presentation, target)

	""" Requesting node information """
	def send_presentation_request(self, target):
		presentation_request = self._build_presentation() + "|" + "WHO"
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

	def not_self(self, node):
		return node[0] != self.node['id']

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
		payload = self._build_presentation() + "|" + "PING|" + str(listening_port)
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
			if verbose == 1:
				print(str(e))
			pass
		except IndexError as ei:
			""" Did not respond """
			pass
		""" Something went wrong """
		return -1

	""" Register sender in corresponding kbucket """
	def register_sender(self, sender, message):
		sender_id = ''
		sender_port = 0

		sender_id, sender_port = self.process_message(message)
		""" Add sender address and port """
		sender_info = (sender_id, sender[0], sender_port)
		self.kbuckets.register_contact(sender_id, sender[0], sender_port)

	def run(self, kbuckets_full_path=''):
		must_shutdown = False

		try:
			if verbose == 1:
				print("Running node " + str(self.node['id']) + " on UDP port " + str(int(self.socket.getsockname()[1])))
			while not must_shutdown:
					result = select.select([self.socket],[],[])
					""" Receive on first and only listening socket """
					msg, sender = result[0][0].recvfrom(2048)
					self._handle_message(msg, sender)
		except KeyboardInterrupt:
			""" Clean shutdown """
			must_shutdown = True
			pass
		except Exception as e:
			""" Something went wrong, log it """
			if verbose == 1:
				print(str(e))
			pass

		""" Save node on disk """
		try:
			filename = 'data/node.json'
			os.makedirs(os.path.dirname(filename), exist_ok=True)
			with open(filename, 'w+') as node_file:
				json.dump(self.node, node_file)
		except:
			if verbose == 1:
				print("Could not save node configuration")
			pass

def generate_hash(data):
	return hashlib.sha256(data.encode('UTF-8')).hexdigest()
