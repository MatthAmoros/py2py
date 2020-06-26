#!/usr/bin/env python
#encoding: utf-8
import os
import base64
import hashlib
import re

from app.config import id_length, max_expiry
from app.constants import *

""" Contains regex based parameters extraction
and common methods for distance caculation """

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

""" Regex to handle message digest """
def extract_key_value_from_store_message(message):
	if message is not None:
		if "STORE|" in message:
			pattern_key = r"STORE\|([^|]*)"
			pattern_value = r"STORE\|[^\|]*[\|]{1}([^\|]*)"

			return re.findall(pattern_key, message)[0], re.findall(pattern_value, message)[0]

def extract_key_from_find_value_message(message):
	if message is not None:
		if "FIND_VALUE|" in message:
			pattern_key = r"FIND_VALUE\|([^|]*)"

			return re.findall(pattern_key, message)[0]

def extract_id_from_find_node_message(message):
	if message is not None:
		if "FIND_NODE|" in message:
			pattern_key = r"FIND_NODE\|([^|]*)"

			return re.findall(pattern_key, message)[0]

def extract_sender_id_contact_from_presentation_message(message):
	id = ""
	contact = ""
	if message is not None:
		if "ID|" in message:
			pattern_id = r"ID\|([^|]*)"
			id = re.findall(pattern_id, message)[0]
		if "AT|" in message:
			pattern_contact = r"AT\|([^|]*)"
			contact = re.findall(pattern_contact, message)[0]

	return id, contact
