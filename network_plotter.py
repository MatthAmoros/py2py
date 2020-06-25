import sys
import json
import matplotlib.pyplot as plt
import numpy as np
from app.config import id_length, k_depth, min_contact, ip_address, answer_ping_behavior, interest_radius, verbose
from app.kbucket import Kbucket
from app.utils import *

execution_path = os.getcwd()
kbucket_by_node_id = {}
connections_ranking = {}
mid_length = id_length * 8 / 2
iteration = 0
plot_source_only = False

if len(sys.argv) > 1:
	source = sys.argv[1]

	""" Check data directory """
	for dir in os.walk(execution_path + '/data'):
		if len(dir[1]) > 0:
			""" One subdirectory for each node, load Kbucket """
			for node in dir[1]:
				""" Add node and kbucket """
				kbucket_by_node_id[node] = Kbucket(node_id = node, id_length = len(node)/2)
				kbucket_by_node_id[node].load_kbuckets()

	node_count = len(kbucket_by_node_id)
	range = np.linspace(0, id_length*8, node_count, endpoint=True)
	node_postion_by_id = {}
	distances = np.zeros(node_count)
	labels = list()

	for node in kbucket_by_node_id:
		""" Calculte distance from source and plot node """
		distance = compute_distance(source, node, id_length)
		distances[iteration] = distance
		""" Register position """
		node_postion_by_id[node] = range[iteration]
		iteration = iteration + 1
		labels.append(node)

	for node_id in node_postion_by_id:
		""" Save current node position """
		connections_ranking[node_id] = len(kbucket_by_node_id[node_id].get_all_known_nodes())
		if node_id == source or not plot_source_only:
			for known_node in kbucket_by_node_id[node_id].get_all_known_nodes():
				""" Plot each known node in our kbucket """
				""" Sample entry ['988df054', '127.0.0.1', '56581'] """
				known_node_id = known_node[0]
				if known_node_id in node_postion_by_id:
					""" Compute line points """
					x_pos = (node_postion_by_id[known_node_id], node_postion_by_id[node_id])
					y_pos = (compute_distance(source, known_node_id, id_length), compute_distance(source, node_id, id_length))
					""" Plot """
					plt.plot(x_pos, y_pos, marker='x')

	plt.plot(range, distances, marker='.')
	plt.title("Connection POV " + source)
	""" Plot center """
	plt.legend(labels)
	print("Connections ranking:")
	for node_id in connections_ranking:
		print(node_id + '->' + str(connections_ranking[node_id]))
	plt.show()
else:
	print("Arguments: Source node ID")
