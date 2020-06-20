#!/usr/bin/env python
#encoding: utf-8
from app.constants import *
"""
	Configuration
"""
""" Byte length """
id_length = 4
""" Node ID length correpsonding to prefix (used to compute distance) """
group_prefix = 10
""" kbuckets max length (peers count per bucket) """
k_depth = 20
""" kbuckets min length (peers count per bucket), used to maintain a minimum peers count for farther distance """
min_contact = 5
""" IP Address """
ip_address = '127.0.0.1'
""" Interes radius """
""" This parameters is used to check if we have an interes to store a topic, according to its distance """
""" If distance_from_me(topic) < interest_radius => store """
""" id_length * 8 = full replication, store everything """
interest_radius = id_length * 8
""" Concurrency parameter """
""" Controls how many FIND_NODE this node will execute in paralal while finding another node """
concurrency_level = 3
""" Store """
""" Max expiry time in hour for key/value pair """
max_expiry = 48

""" Security configuration """
""" Answer PING """
""" 0 = Never """
""" 1 = Trusted only """
""" 2 = Always """
answer_ping_behavior = ANSWER_PING_ALWAYS
""" Use same return route """
""" 0 = False, route response throught a different route that the incomming one """
""" 1 = True, route response throught fastest route (could include original incomming route) """
use_same_return_route = 1

""" Debug """
verbose = 0

debug = True
