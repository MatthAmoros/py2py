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
from data.config import id_length, group_prefix, max_contact, min_contact, ip_address, answer_ping_behavior, interest_radius
from app.kbucket import Kbucket
from app.constants import *

class Node:
	""" Try load node and context """
	node_loaded = 0
	kbuckets_loaded = 0
	socket = None

	kbuckets = Kbucket(node_id='', id_length=id_length)
	node = {}

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
			self.node['id'] = os.urandom(id_length).hex()

		port = 0

		if 'port' in self.node:
			port = int(self.node['port'])

		""" Initialize socket """
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

		try:
			self.socket.bind((ip_address,port))
		except socket.error as e:
			if e.errno == errno.EADDRINUSE:
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
			""" Get topic """
			""" GET|XXXXXX|FOR|XXXXXX """
			self.send_topic(sender, message)
		if 'TOP' in message:
			""" Found topic """
			if 'FOR' in message:
				""" Forward """
				self.handle_forward(sender, message)
			else:
				print("Found: "+ str(message))
		if 'NOP' in message:
			""" Not found """
			if 'FOR' in message:
				""" Forward """
				self.handle_forward(sender, message)
			else:
				print("Not found: "+ str(message))
		if 'ROUT' in message:
			""" Route information """
			""" ROUT|[NODE ID]|[IP]|[PORT] """
			self.handle_route_information(message)
		if 'INFO' in message:
			""" A peer is informing of a new topic """
			self.handle_topic_information(message)

	def handle_route_information(self, message):
		new_contact = message.split('|')[1:-1]
		print(new_contact)

	def handle_forward(self, sender, message):
		if 'FOR' in message:
			destination_node_id = message.split('|')[-1]
			""" Check that it's for us """
			if destination_node_id == self.node['id']:
				""" Remove forward flag, resend to self """
				message = message.replace('|FOR|' + str(destination_node_id), '')
				print("handle_forward:: Is for me " + str(message))
				self.send_payload(message, self.node['id'])
			else:
				""" Forward """
				print("handle_forward:: Forward " + str(message))
				self.send_payload(message, destination_node_id)

	def get_topic(self, topic):
		payload = self.build_presentation() + "|GET|" + str(topic) + "|FOR|" + self.node['id']
		""" Send to ourself """
		self.send_topic(('127.0.0.1', self.node['port']), payload)

	def handle_topic_information(self, message):
		""" Handle topic information """
		sender_id, sender_port = self.process_message(message)
		""" Remove header """
		message = message.replace('ID|' + str(sender_id) + '|AT|' + str(sender_port) + '|', '')
		""" INFO|493b1310|AT|87f1640e """
		""" Extract topic_id """
		topic_id, sender_id = message.split('|')[1], message.split('|')[3]
		if self.kbuckets.is_of_interest(topic_id):
			payload = self.build_presentation() + "|GET|" + str(topic_id) + "|FOR|" + self.node['id']
			self.send_topic(sender_id, payload)
		else:
			print("handle_topic_information:: Skipping, out of radius")

	def add_topic(self, topic_id, data):
		""" Add topic to known topics """
		data = topiquify_data(data)
		data = (topic_id, data)
		""" Delete for update """
		self.kbuckets.try_delete_topic(topic_id)

		self.inform_topic(topic_id)
		self.kbuckets.register_topic(topic_id, data)

	def inform_topic(self, topic_id):
		""" Inform network of a new available topic """
		""" Inform closest only """
		closest_node = self.kbuckets.get_closest_known_node(topic_id, allow_matching_exact=False)
		if closest_node is not None:
			self.send_inform_topic(closest_node[0], topic_id)
		else:
			print("inform_topic:: No nodes.")

	def send_inform_topic(self, target, topic_id):
		""" Send topic id """
		payload = self.build_presentation() + "|INFO|" + str(topic_id) + "|AT|" + self.node['id']
		self.send_payload(payload, target)

	""" Lookup topic and send response """
	""" If topic is found in known object, return response to original sender """
	""" Else, forward to closest node """
	def send_topic(self, sender, message):
		payload = self.build_presentation()
		sender_id, _ = self.process_message(message)
		node_origin_id = message.split('|')[-1]
		topic = message.split('|')[-3]
		closest_node = self.kbuckets.get_closest_known_node(topic)
		print("send_topic:: Looking for [" + str(topic) + "]")
		if closest_node is None:
			print("send_topic:: Nothing found.")
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
				print("send_topic:: Found, send response to original sender")
				self.send_payload(payload, node_origin_id)
			elif closest_node[0] != node_origin_id and closest_node[0] != sender_id:
				""" Didn't found requested node, forward to closest that is not sender nor original sender """
				payload = self.build_presentation() + "|GET|" + topic + "|FOR|" + node_origin_id
				print("send_topic:: Topic not known, sending to closest: " + str(closest_node))
				self.send_payload(payload, (closest_node[1], int(closest_node[2])))
			else:
				print("send_topic:: Nothing found.")
				payload = payload + "|NOP|" + str(topic) + "|FOR|" + node_origin_id
				self.send_payload(payload, node_origin_id)
		elif len(closest_node) == 2:
			""" Data topic """
			payload = payload + "|TOP|" + closest_node[1] + "|FOR|" + node_origin_id
			print("send_topic:: Found, send response to original sender")
			self.send_payload(payload, node_origin_id)
		else:
			print("send_topic:: Not connected to py2py network.")

	""" Return header or presentation message containing ID and UDP port """
	def build_presentation(self):
		return "ID|" + str(self.node['id']) + "|AT|" + str(self.node['port'])

	""" Respond to ping request """
	def send_pong(self, target, message):
		if answer_ping_behavior == ANSWER_PING_ALWAYS \
		or answer_ping_behavior == ANSWER_PING_TRUSTED:
			if answer_ping_behavior == ANSWER_PING_TRUSTED:
				if self.is_trusted(target):
					ping_port = int(message.split('|')[-1])
					payload = self.build_presentation() + "|" + "PONG"
					print("send_pong:: Sending pong to " + str(target[0]) + ":" + str(ping_port))
					self.send_payload(payload=payload, target=(target[0], int(ping_port)))
			else:
				ping_port = int(message.split('|')[-1])
				payload = self.build_presentation() + "|" + "PONG"
				print("send_pong:: Sending pong to " + str(target[0]) + ":" + str(ping_port))
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
				""" Extract IP / Port """
				print("send_payload:: Node ID [" + target + "] not known, sending to closest: " + str(closest_node))
				target = (closest_node[1], int(closest_node[2]))

		print("send_payload:: Sending [" + str(payload) + "] to: " + str(target))
		with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
			sock.sendto(encoded, target)

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
		if len(kbuckets_full_path) > 0:
			self.kbuckets.load_kbuckets(kbuckets_full_path)
		else:
			self.kbuckets.load_kbuckets()

		try:
			print("Running node " + str(self.node['id']) + " on UDP port " + str(int(self.socket.getsockname()[1])))
			while not must_shutdown:
					result = select.select([self.socket],[],[])
					""" Receive on first and only listening socket """
					msg, sender = result[0][0].recvfrom(2048)
					self.handle_message(msg, sender)
		except KeyboardInterrupt:
			""" Clean shutdown """
			must_shutdown = True
			pass
		except Exception as e:
			""" Something went wrong, log it """
			print(str(e))
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

def topiquify_data(data):
	return hashlib.sha256(data.encode('UTF-8')).hexdigest()
