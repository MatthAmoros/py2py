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
from app.event import Event
from app.config import id_length, group_prefix, max_contact, min_contact, ip_address, answer_ping_behavior, interest_radius
from app.kbucket import Kbucket
from app.constants import *

class Store:
	__store = {}
	__on_add_key_event = Event()

	def add_key_value(self, key, value):
		self.__store[key] = value

	def get_value(self, key):
		if key in self.__store:
			return self.__store[key]
		else:
			return ''
