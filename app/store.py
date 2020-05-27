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
from app.constants import *

class Store:
	__store = {}
	__on_add_key_event = Event()
	__current_node_id = ''

	def __init__(self, node_id=''):
		self.__current_node_id = node_id
		self.load()

	def add_key_value(self, key, value):
		self.__store[key] = value
		self.save()

	def get_value(self, key):
		if key in self.__store:
			return self.__store[key]
		else:
			return ''

	def load(self, filepath=''):
		""" Load store from file """
		if filepath == '':
			filepath = 'data/' + self.__current_node_id + '/store.json'
		try:
			with open(filepath) as store_file:
				self.__store = json.load(store_file)
		except:
			self.__store = {}
			pass

	def save(self):
		""" Save store on disk """
		try:
			filename = 'data/' + self.__current_node_id + '/store.json'
			os.makedirs(os.path.dirname(filename), exist_ok=True)
			with open(filename, 'w+') as store_file:
				json.dump(self.__store, store_file)
		except:
			print("Could not save store on disk.")
			pass
