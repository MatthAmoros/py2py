#!/usr/bin/env python
#encoding: utf-8

from app.config import concurrency_level, id_length, debug, group_prefix, k_depth, min_contact, ip_address, answer_ping_behavior, interest_radius, verbose
from app.constants import *
from app.utils import *

class RequestsTracker:
	def __init__(self, associated_node_id=''):
		""" Initialize stack """
		self.requests_queue = list()
		self.associated_node_id = associated_node_id

	def add_tracking(self, tracked_id='', max_distance=id_length*8, callback=None, tracked_by=None):
		self.requests_queue.append(Request(tracked_id, max_distance, tracked_by, callback))

	def remove_tracking(self, tracked_id=''):
		for request in self.requests_queue:
			if request.tracked_id == tracked_id:
				self.requests_queue.remove(request)

	def notify_tracker(self, new_id=''):
		for request in self.requests_queue:
			request.iteration = request.iteration + 1

			""" Get distance between incomming node and tracked node """
			distance = compute_distance(request.tracked_id, new_id, id_length=id_length)
			""" Closer than max distance or found? """
			if request.tracked_id == new_id or distance < request.max_distance:
				""" Tracked id found, inform and update max_distance with new one """
				if request.callback:
					request.callback(tracked_id=request.tracked_id, tracked_by=request.tracked_by, max_distance=distance)
					request.max_distance = distance

			if request.iteration > k_depth or request.max_distance == 0:
				""" It has been too long or we found it, remove tracker """
				self.requests_queue.remove(request)

class Request:
	def __init__(self,
	tracked_id='',
	max_distance=id_length*8,
	tracked_by=None,
	callback=None):
		self.tracked_id = tracked_id
		self.max_distance = max_distance
		self.callback = callback
		self.tracked_by = tracked_by
		self.iteration = 0
