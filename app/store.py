#!/usr/bin/env python
#encoding: utf-8

import json
import os
import errno
import base64
import hashlib
import itertools
from datetime import datetime, timedelta
from app.event import Event
from app.config import id_length, max_expiry, debug
from app.utils import compute_distance
from app.constants import *

class Store:
	""" Store key/value pairs """
	__store = {}
	""" Store expiry data for each key """
	__expiry_by_key = {}
	__on_add_key_event = Event()
	__current_node_id = ''

	def __init__(self, node_id=''):
		self.__current_node_id = node_id
		self.load()

	def add_key_value(self, key, value):
		""" Add key value to store and set expiry """
		already_exists = False
		already_exists = (key in self.__store and self.__store[key] == value)

		""" Set or update expiry date """
		expiry_value = self.calculate_expiry(key)
		if debug == 0:
			expiry_date = datetime.now() + timedelta(hours=expiry_value)
		else:
			""" Set expiry in seconds during debug mode """
			expiry_date = datetime.now() + timedelta(seconds=expiry_value)

		self.__expiry_by_key[key] = expiry_date

		""" If not exists, add to store """
		if not already_exists:
			self.__store[key] = value
			self.save()

		return already_exists

	""" Get value by key """
	def get_value(self, key):
		if key in self.__store:
			if key in self.__expiry_by_key:
				if self.__expiry_by_key[key] > datetime.now():
					return self.__store[key]
			""" Expired or some error occured, delete key/value """
			del self.__store[key]
		else:
			return ''

	""" Load store from file """
	def load(self, filepath=''):
		""" Load store and expiry from file """
		if filepath == '':
			filepath = 'data/' + self.__current_node_id + '/store.json'
		try:
			with open(filepath) as store_cfile:
				self.__store = json.load(store_file)
		except:
			self.__store = {}
			pass

		if filepath == '':
			filepath = 'data/' + self.__current_node_id + '/store_expiry.json'
		try:
			with open(filepath) as store_expiry_cfile:
				self.__expiry_by_key = json.load(store_expiry_cfile)
		except:
			self.__expiry_by_key = {}
			pass

	""" Save store to file """
	def save(self):
		""" Save store and expiry on disk """
		try:
			filename = 'data/' + self.__current_node_id + '/store.json'
			os.makedirs(os.path.dirname(filename), exist_ok=True)
			with open(filename, 'w+') as store_file:
				json.dump(self.__store, store_file)
		except:
			print("Could not save store on disk.")
			pass

		try:
			filename = 'data/' + self.__current_node_id + '/store_expiry.json'
			os.makedirs(os.path.dirname(filename), exist_ok=True)
			with open(filename, 'w+') as store_expiry_file:
				json.dump(self.__expiry_by_key, store_expiry_file, default=str)
		except:
			print("Could not save store_expiry on disk.")
			pass

	""" Calculate experiation by key """
	def calculate_expiry(self, key):
		""" Return expiry date according to key distance """
		distance = compute_distance(self.__current_node_id, key, id_length)
		""" Expiry should be longer when distance is closer """
		expiry = int((max_expiry - (distance / id_length * max_expiry)) + 1)

		return expiry
