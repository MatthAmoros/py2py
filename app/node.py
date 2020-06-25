#!/usr/bin/env python
#encoding: utf-8

import json
import os
import errno
import time
import socket
import select
import base64
import hashlib
import itertools
import threading
from app.config import concurrency_level, id_length, debug, group_prefix, k_depth, min_contact, ip_address, answer_ping_behavior, interest_radius, verbose
from app.requests_tracker import RequestsTracker
from app.kbucket import Kbucket
from app.store import Store
from app.constants import *
from app.utils import *

class Node:
	""" Try load node and context """
	node_loaded = 0
	kbuckets_loaded = 0
	socket = None

	kbuckets = None
	node = {}
	_store = None
	tracker = None

	def __init__(self, node_id='', port=0):
		""" Load node configuration from file """
		try:
			if not debug:
				with open('data/node.json') as node_file:
					self.node = json.load(node_file)
					self.node_loaded = 1
		except:
			pass

		""" Generate bit ID and digest """
		if self.node_loaded == 0:
			self.node['id'] = generate_hash(str(os.urandom(id_length).hex()))
			self.node['port'] = 0
			self.node['ip'] = ip_address
			self.node_loaded = 1

		""" Initilize requests tracker """
		self.tracker = RequestsTracker()
		""" Initialize kbucket """
		self.kbuckets = Kbucket(node_id=self.node['id'], id_length=id_length)
		self.kbuckets.load_kbuckets()

		""" Initialize store """
		self._store = Store(node_id=self.node['id'])

		""" Initialize socket """
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

		""" Try bind socket """
		try:
			self.socket.bind((ip_address, int(self.node['port'])))
		except socket.error as e:
			if e.errno == errno.EADDRINUSE:
				self.socket.bind((ip_address,0))
				if verbose == 1:
					print(self.node['id']+ "::listen " + str(self.node['port']) + " already in use.")
			pass

		""" Save current port """
		self.node['port'] = int(self.socket.getsockname()[1])

	""" Main entry point for message coming into UDP socket """
	def _handle_message(self, message, sender):
		""" Handle incomming message """
		""" Message header should be "ID|XXXXXXXXXXXXXXXXXXXXX|AT|XXXXXX" """
		message = base64.b64decode(message).decode('ASCII')
		if verbose == 1:
			print(self.node['id'] + "|_handle_message:: Received " + message + " from " + str(sender[0]))

		if 'ID' in message:
			self.register_sender(sender, message)
			if 'BOOT' in message:
				""" Bootstrap new node """
				self._send_bootstrap_information(sender, message)
			if 'PING' in message:
				self._send_pong(sender, message)
			if 'STORE' in message:
				""" Called to store a key/value pair or to answer FIND_VALUE/FIND_NODE/BOOT request """
				""" STORE|KEY|VALUE """
				self._store_key_pair(sender, message)
			if 'FIND_NODE' in message:
				""" Get topic """
				""" FIND_NODE|XXXXXX """
				self._send_node_info(sender=sender, message=message)
			if 'FIND_VALUE' in message:
				""" Get topic """
				""" FIND_VALUE|XXXXXX"""
				self._send_key_value_response(sender, message)

			if 'NOP' in message:
				""" Not found """
				if verbose == 1:
					print(message)

	""" Send contact list to new node """
	def _send_bootstrap_information(self, sender, message):
		sender_id, _ = extract_sender_id_contact_from_presentation_message(message)
		nodes = self.kbuckets.get_closest_known_nodes(sender_id)
		for node in nodes:
			if sender_id != node[1][0]:
				""" Send ID and CNT-[IP]:[PORT] as value """
				self.store(sender_id, node[1][0], 'CNT-' + str(node[1][1]) + '@' + str(node[1][2]))

	""" Query a node for bootstrap information (contact list) """
	def send_bootstrap_request(self, target):
		bootstrap_request = self._build_presentation() + "|BOOT|AT|" + str(self.node['port'])
		self.send_payload(bootstrap_request, target)

	""" Order a node to store a key value pair """
	def store(self, target, key, value):
		store_request = self._build_presentation() + "|STORE|" + key + "|" + value
		self.send_payload(store_request, target)

	""" Store a key value pair from received message """
	def _store_key_pair(self, sender, message):
		already_exists = True
		key, value = extract_key_value_from_store_message(message)

		if 'CNT-' in value:
			""" We received a contact """
			contact_id = key
			contact_ip = value.replace('CNT-', '').split('@')[0]
			contact_port = value.replace('CNT-', '').split('@')[1]
			already_exists = self.kbuckets.register_contact(contact_id, contact_ip, int(contact_port))
		else:
			already_exists = self.store_key_pair(key=key, value=value)
		self.tracker.notify_tracker(new_id=key)

		if not already_exists:
			self.send_replication(key=key, value=value)

	""" Store a key value pair """
	def store_key_pair(self, key, value):
		already_exists = self._store.add_key_value(key, value)
		if verbose == 1:
			print("store_key_pair::add_key_value:: Stored [" + str(key) + "]:" + str(value) + " at node [" + self.node['id'] + "]")
		""" Forward to closest nodes """
		if not already_exists:
			self.send_replication(key, value)

	""" Send key/value pair to closest nodes for replication """
	def send_replication(self, key, value):
		closest_nodes = self.kbuckets.get_closest_known_nodes(key)
		for node in closest_nodes:
			#print("send_replication:: Sending to " + str(node[1][0]) + " key/value " + str(key) + '/' + str(value))
			self.store(target=node[1][0], key=key, value=value)

	""" Check if key has an associated value in local storage """
	def has_in_local_store(self, key):
		return self._store.get_value(key)

	""" Send FIND_VALUE request """
	def find_value(self, target, key, callback=None):
		self.tracker.add_tracking(tracked_id=key, callback=callback)
		find_value_request = self._build_presentation() + "|FIND_VALUE|" + key
		self.send_payload(find_value_request, target)

	""" Send resposne to FIND_VALUE query """
	def _send_key_value_response(self, sender, message):
		sender_id, _ = extract_sender_id_contact_from_presentation_message(message)
		key = extract_key_from_find_value_message(message)
		found_value = self._store.get_value(key)

		if len(found_value) > 0:
			""" Found """
			response_payload = self._build_presentation() + "|STORE|" + key + "|" + found_value
			self.send_payload(response_payload, sender_id)

	""" Send FIND_NODE request """
	def find_node(self, node_id='', callback=None):
		""" Add tracking and create callback for further results """
		def find_node_follow_up(tracked_id, closest_id, max_distance, tracked_by=None):
			print("::find_node_follow_up Received data on " + str(tracked_id) + ", more info at " +  str(closest_id) + "|" + str(max_distance))
			""" Send follow up FIND_NODE requests """
			payload = tracked_by._build_presentation() + "|FIND_NODE|" + str(tracked_id)
			tracked_by.send_payload(target=closest_id, payload=payload)
		self.tracker.add_tracking(tracked_id=node_id, tracked_by=self, follow_up=find_node_follow_up, callback=callback)
		payload = self._build_presentation() + "|FIND_NODE|" + str(node_id)
		""" Send to ourself """
		self._send_node_info(('127.0.0.1', self.node['port']), payload)

	""" Lookup topic and send response """
	""" If topic is found in known object, return response to original sender """
	""" Else, forward to closest node """
	def _send_node_info(self, sender, message):
		payload = self._build_presentation()
		sender_id, _ = extract_sender_id_contact_from_presentation_message(message)
		node_id = extract_id_from_find_node_message(message)
		closest_nodes = self.kbuckets.get_closest_known_nodes(node_id)

		if verbose == 1:
			print(str(self.node['id']) + "|_send_node_info:: Looking for [" + str(node_id) + "]")

		if closest_nodes is None or len(closest_nodes) < k_depth:
			if verbose == 1:
				print(str(self.node['id']) + "|_send_node_info:: Found [" + str(closest_nodes) + "]")
			if verbose == 1:
				print("_send_node_info:: Nothing found or not enough results.")
			""" Forward to closest node to get more results """
			for node_info_by_dist in closest_nodes:
				""" Each node is stored with its distance """
				""" (160, ('16b4006bbd4146edc3b2cf7d862a39bc87ea0b7df0f6ca0cde3c11a7b16953d2', '127.0.0.1', '33697')) """
				node_info = node_info_by_dist[1]
				self.send_payload("ID|" + node_info[0] + "|AT|" + node_info[1] + ":" + str(node_info[2]), sender_id)

	""" Return header or presentation message containing ID and UDP port """
	def _build_presentation(self):
		return "ID|" + str(self.node['id']) + "|AT|" + self.node['ip'] + ":" + str(self.node['port'])

	""" Respond to ping request """
	def _send_pong(self, sender, message):
		sender_id, _ = extract_sender_id_contact_from_presentation_message(message)
		self.send_payload(self._build_presentation(), sender_id)

	def is_trusted(self, node):
		return False

	""" A node is connected when it knows at least one peer """
	def is_connected(self):
		return not self.kbuckets.is_empty()

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
			print(self.node['id'] + "|send_payload:: Sending [" + str(payload) + "] to: " + str(target))
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
		sender_ip = '127.0.0.1'

		""" Static search for parameters """
		if properties[0] == "ID":
			sender_id = properties[1]

		if properties[2] == "AT":
			if ':' in properties[3]:
				sender_ip, sender_port = properties[3].split(':')
			else:
				sender_port = properties[3]

		return sender_id, sender_port, sender_ip

	def not_self(self, node):
		return node[0] != self.node['id']

	""" Try reach node, timeout 500 ms """
	""" Returns 0 on success """
	def ping(self, node_info):
		""" Send ping request """
		payload = self._build_presentation() + "|" + "PING"
		self.send_payload(payload, (node_info[1], int(node_info[2])))

	""" Register sender in corresponding kbucket """
	def register_sender(self, sender, message):
		sender_id = ''
		sender_port = 0

		sender_id, sender_port, sender_ip = self.process_message(message)
		""" Add sender address and port """
		sender_info = (sender_id, sender_ip, sender_port)
		self.kbuckets.register_contact(sender_id, sender_ip, sender_port)
		self.tracker.notify_tracker(new_id=sender_id)

	def run_listener(self, kbuckets_full_path=''):
		self.listener_thread = threading.Thread(target=listen, args=(self,))

		try:
			self.listener_thread.running = True
			self.listener_thread.start()
		except Exception as e:
			""" Something went wrong, log it """
			if verbose == 1:
				print(str(e))
			self.listener_thread.running = False
			pass

		""" Save node on disk """
		if not debug:
			try:
				filename = 'data/node.json'
				os.makedirs(os.path.dirname(filename), exist_ok=True)
				with open(filename, 'w+') as node_file:
					json.dump(self.node, node_file)
			except:
				if verbose == 1:
					print("Could not save node configuration")
				pass

	def save_properties(self):
		self.kbuckets.save()
		self._store.save()

	def shutdown(self):
		self.listener_thread.running = False
		self.listener_thread.join()

""" Should run in a separated thread """
def listen(node):
	t = threading.currentThread()
	if verbose == 1:
		print("Running node " + str(node.node['id']) + " on UDP port " + str(node.socket.getsockname()[1]))

	while getattr(t, "running", True):
		try:
			""" Timeout of 1 sec """
			result = select.select([node.socket],[],[], 1)
			""" Receive on first and only listening socket on this port """
			if len(result[0]) > 0:
				""" On our port (used in case multiple node were sharing same thread) """
				msg, sender = result[0][0].recvfrom(2048)
				node._handle_message(msg, sender)
		except socket.timeout:
			pass
	if verbose == 1:
		print("Listener shutting down.")

def generate_hash(data):
	if id_length == 20:
		return hashlib.sha256(data.encode('UTF-8')).hexdigest()
	else:
		return str(os.urandom(id_length).hex())
