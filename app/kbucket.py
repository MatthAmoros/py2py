#!/usr/bin/env python
#encoding: utf-8
import os
import json
from app.config import id_length, group_prefix, k_depth, min_contact, ip_address, answer_ping_behavior, interest_radius, debug

class Kbucket:
	__structure = {}
	__current_node_id = ''
	__id_length = 8

	def __init__(self, node_id = '', id_length = 8):
		self.__current_node_id = node_id
		self.__id_length = id_length

	def load_kbuckets(self, filepath=''):
		""" Load kbuckets from file """
		if filepath == '':
			filepath = 'data/' + self.__current_node_id + '/kbuckets.json'
		try:
			with open(filepath) as kbuckets_file:
				self.__structure = json.load(kbuckets_file)
				kbuckets_loaded = 1
		except:
			""" Init empty kbuckets """
			for distance in range(0, self.__id_length*8 + 1):
				self.__structure[distance] = list()
			pass

		print("Kbuckets reloaded")

	""" True if kbucket is empty """
	def is_empty(self):
		nodes = self.get_all_known_nodes()
		return len(nodes) == 0

	""" Returns distance from current node """
	def distance_from_me(self, target_id):
		return compute_distance(self.__current_node_id, target_id, self.__id_length)

	""" Flatten kbuckets """
	def get_all_known_nodes(self):
		all_node = list()
		for i in self.__structure:
			for node in self.__structure[i]:
				all_node.append(node)

		return all_node

	def known_contacts_count(self):
		return len(self.get_all_known_nodes())

	""" Returns list of k closest node """
	def get_closest_known_nodes(self, target_id):
		distance_by_node = list()

		all_nodes = self.get_all_known_nodes()
		for _node in all_nodes:
			dist = compute_distance(_node[0], target_id, self.__id_length)
			distance_by_node.append((dist, _node))

		""" Sort by distance, closest first """
		sorted_nodes = sorted(distance_by_node, key=lambda x: x[0], reverse=False)

		if len(sorted_nodes) > k_depth:
			return sorted_nodes[:k_depth]
		else:
			return sorted_nodes

	""" Get closest node to target node id """
	""" Returns full node description (id, ip, port) """
	def get_closest_known_node(self, target_id, allow_matching_exact=True):
		""" Check if kbuckets exists """
		if len(self.__structure) == 0:
			default_path = 'data/' + self.__current_node_id + '/kbuckets.json'

		distance = self.distance_from_me(target_id)
		""" Get corresponding bucket """
		if distance in self.__structure:
			kbucket = self.__structure[distance]
		else:
			""" Empty """
			kbucket = list()

		""" Init to max distance """
		min = self.__id_length * 8 + 1
		closest_node = None

		if len(kbucket) > 0:
			for _node in kbucket:
				tmp = compute_distance(_node[0], target_id, self.__id_length)
				if tmp < min:
					min = tmp
					closest_node = _node
		else:
			""" Check for closest node, without filtering bucket """
			all_nodes = self.get_all_known_nodes()
			for _node in all_nodes:
				tmp = compute_distance(_node[0], target_id, self.__id_length)
				#print("get_closest_known_node:: Node [" + str(_node[0]) + "] distance: " + str(tmp) + " from destination [" + str(target_id) +  "]")
				if tmp < min and allow_matching_exact:
					min = tmp
					closest_node = _node
				elif tmp < min and not allow_matching_exact:
					if tmp == 0:
						continue
					else:
						min = tmp
						closest_node = _node
		return closest_node

	def is_contact_node(node_id):
		return len(node_id) == self.__id_length

	""" Check if topic is of interest """
	def is_of_interest(self, topic_id):
		return self.distance_from_me(topic_id) <= interest_radius

	""" Check if contact exists and return index """
	def topic_exists(self, contact_id, distance):
		index = 0
		kbucket = self.__structure[distance]
		print("topic_exists:: Loading kbuckets " + str(distance))
		for contact in kbucket:
			if contact[0] == contact_id:
				return index
			index = index + 1

		return -1

	def register_topic(self, topic_id, data):
		if topic_id == self.__current_node_id:
			""" Never store self """
			return

		""" Refresh kbuckets """
		self.load_kbuckets()

		""" Compute distance between nodes (XOR) """
		distance = self.distance_from_me(topic_id)
		contact_limit = get_max_bucket_peers(distance, self.__id_length)
		distance = str(distance)
		if distance not in self.__structure:
			print("register_topic:: New bucket for ditance: " + str(distance))
			self.__structure[distance] = list()

		""" Contact already exists """
		topic_index = self.topic_exists(topic_id, distance)
		if topic_index > -1:
			""" Delete it, it will be added at the end of the list during next step """
			del self.__structure[distance][topic_index]

		""" We have more than max contact count """
		if len(self.__structure[distance]) >= contact_limit:
				del self.__structure[distance][0]
				self.__structure[distance].append(data)
		else:
			self.__structure[distance].append(data)

		print("register_topic:: Registered [" + topic_id + "] - [" + str(data) + "] in kbucket " + str(distance))
		if debug == 0:
			""" Only save on explicit calls while in debug """
			self.save()

	def save(self):
		""" Save kbuckets on disk """
		try:
			filename = 'data/' + self.__current_node_id + '/kbuckets.json'
			os.makedirs(os.path.dirname(filename), exist_ok=True)
			with open(filename, 'w+') as kbuckets_file:
				json.dump(self.__structure, kbuckets_file)
		except:
			print("Could not save kbuckets on disk.")
			pass

	def try_delete_topic(self, topic_id):
		distance = self.distance_from_me(topic_id)
		if distance not in self.__structure:
			self.__structure[distance] = list()
		""" Topic already exists """
		topic_index = self.topic_exists(topic_id, distance)
		if topic_index > -1:
			""" Delete it, it will be added at the end of the list during next step """
			del self.__structure[distance][topic_index]

	def register_contact(self, contact_id, contact_address, contact_port):
		""" Add sender address and port """
		contact_info = (contact_id, contact_address, contact_port)
		self.register_topic(contact_id, contact_info)

""" Returns max contact per bucket according to distance """
def get_max_bucket_peers(distance, id_length):
	limit = k_depth

	""" Max bucket count is lenght of id in bit """
	max_buckets = id_length * 8

	""" For short distance we want to store more contact """
	limit = round(k_depth / max_buckets) * (max_buckets - distance)

	""" Avoid 0, always store at least one contact """
	if limit < min_contact:
		limit = min_contact

	return limit

""" Compute distance using integer XOR """
def compute_distance(node1_id, node2_id, id_length):
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
