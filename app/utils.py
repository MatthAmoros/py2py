#!/usr/bin/env python
#encoding: utf-8
import os
import base64
import hashlib

from app.config import id_length, max_expiry
from app.constants import *

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
