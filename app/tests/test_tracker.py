import pytest
from app.requests_tracker import RequestsTracker
from unittest.mock import MagicMock

def test_notify_tracker():
	tracker = RequestsTracker(associated_node_id='cb9edfff')
	""" Mocked callback to check calls """
	my_callback = MagicMock(return_value=3)
	""" Track FIND_NODE answer with id 123456789 and point to mocked callback """
	tracker.add_tracking(tracked_id='cb9edbb8', callback=my_callback)
	""" Trigger notify """
	tracker.notify_tracker('cb9edbb8')
	""" Assert call """
	my_callback.assert_called_with(max_distance=0, tracked_id='cb9edbb8', tracked_by=None)

def test_removed_tracker():
	tracker = RequestsTracker(associated_node_id='cb9edfff')
	""" Mocked callback to check calls """
	my_callback = MagicMock(return_value=3)
	""" Track FIND_NODE answer with id 123456789 and point to mocked callback """
	tracker.add_tracking(tracked_id='cb9edbb8', callback=my_callback)
	""" Remove tracker """
	tracker.remove_tracking(tracked_id='cb9edbb8')
	""" Trigger notify """
	tracker.notify_tracker('cb9edbb8')
	""" Assert NOT call """
	my_callback.assert_not_called()
