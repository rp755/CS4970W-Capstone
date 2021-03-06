import requests
import datetime
import uuid
import json
import numpy
import copy

from CAT import settings


def register_device(config):
	''' Checks if this device has a valid ID.
		If not, it registers as a new device with the server.
		Parameters:
			config
				CAT.settings.Config - all settings associated with the program
	'''

	# Check if the device ID is valid
	if config.get("device_id") == "None":
		# generate new device ID
		handle = str(uuid.uuid4()) # generates a random ID

		# register the device with the server
		request_data = {"handle": handle}
		response = requests.post("{}/devices".format(config.get("server")), data=request_data)

		# get the new device's ID
		response_data = response.json()
		device_id = response_data["deviceId"]
		settings_id = response_data["settings"]["settingsId"]

		# update the device ID and settings ID outside of process synchronization
		# this function should be called before other processes are started
		# (and do not update the server for changing the device and settings ID)

		# update the settings with the new ID
		config.set("device_id", device_id)

		# update the settings with the new settings ID
		config.set("settings_id", settings_id)


def update_device_settings(config):
	''' Update the settings associated with a device on the server
		Parameters:
			config
				CAT.settings.Config - all settings associated with the program
		Returns:
			str - the new settings ID
	'''

	# update the settings on the server
	request_data = {
		"id": config.get("device_id"),
		"settings": config.to_string()
	}
	response = requests.put("{}/devices/{}/settings".format(config.get("server"), config.get("device_id")), data=request_data)

	# get the new settings ID
	response_data = response.json()
	return response_data["settingsId"]


def register_speaker(config, audio_mean, audio_covariance):
	''' Registers a new speaker with the server
		Parameters:
			config
				CAT.settings.Config - all settings associated with the program
		Returns:
			str - new speaker ID
	'''

	# convert data into a transmittable format
	data = {
		"mean": audio_mean.tolist(), 
		"covariance": audio_covariance.tolist(), 
		"count": 1, 
		"last_seen": datetime.datetime.now().isoformat(),
		"active": True
	}

	# register new speaker
	request_data = {
		"deviceId": config.get("device_id"),
		"data": json.dumps(data)
	}
	response = requests.post("{}/speakers".format(config.get("server")), data=request_data)

	# get the new speakers's ID
	response_data = response.json()
	return response_data["speakerId"]


def get_speakers(config):
	''' Gets the ID and specifications of all speakers registered with this device
		Parameters:
			config
				CAT.settings.Config - all settings associated with the program
		Returns:
			dict - {speaker ID: specifications}
	'''

	response = requests.get("{}/devices/{}/speakers".format(config.get("server"), config.get("device_id")))
	response_data = response.json()
	
	# convert dictionary format
	speaker_dictionary = {}
	for speaker in response_data:
		speaker_data = json.loads(speaker["data"])
		if speaker_data["active"]:
			speaker_dictionary[speaker["speakerId"]] = {
				"mean": numpy.array(speaker_data["mean"]),
				"covariance": numpy.array(speaker_data["covariance"]),
				"count": speaker_data["count"],
				"last_seen": datetime.datetime.strptime(speaker_data["last_seen"], "%Y-%m-%dT%H:%M:%S.%f")
			}

	return speaker_dictionary


def delete_speaker(config, speaker_id):
	''' 
		Parameters:
			config
				CAT.settings.Config - all settings associated with the program
			speaker_id
				str - ID of the speaker to delete
	'''

	# de-activate speaker
	data = {
		"active": False
	}

	request_data = {
		"id": speaker_id,
		"data": json.dumps(data)
	}
	requests.put("{}/speakers/{}".format(config.get("server"), speaker_id), data=request_data)


def update_speaker(config, speaker_id, speaker_mean, speaker_covariance, speaker_count):
	''' Registers a new speaker with the server
		Parameters:
			config
				CAT.settings.Config - all settings associated with the program
		Returns:
			str - new speaker ID
	'''

	# convert data into a transmittable format
	data = {
		"mean": speaker_mean.tolist(), 
		"covariance": speaker_covariance.tolist(), 
		"count": speaker_count, 
		"last_seen": datetime.datetime.now().isoformat(),
		"active": True
	}

	# register new speaker
	request_data = {
		"id": speaker_id,
		"data": json.dumps(data)
	}
	requests.put("{}/speakers/{}".format(config.get("server"), speaker_id), data=request_data)


def transmit(features, speaker, config):
	''' Transmits features extracted from a slice of audio data
		Parameters:
			features
				the features extracted
			speaker
				str - the speaker detect in the audio data
			config
				CAT.settings.Config - all settings associated with the program
	'''

	request_data = {
		"deviceId": config.get("device_id"),
		"settingsId": config.get("settings_id"),
		"recordingTime": datetime.datetime.now().isoformat(),
		"data": json.dumps(features)
	}
	if speaker:
		request_data["speakerId"] = speaker

	response = requests.post("{}/recordings".format(config.get("server")), data=request_data)


def check_for_updates(config, settings_dictionary, threads_ready_to_update, settings_update_event, settings_update_lock):
	''' Updates settings if they need to be updated
		Parameters:
			config
				CAT.settings.Config - all settings associated with the program
			settings_dictionary
				{str: CAT.settings.Config} - all sets of settings associated with the program
			threads_ready_to_update
				multiprocessing.Semaphore - indicates how many threads are currently ready for a settings update
			setting_update_event
				multiprocessing.Event - indicates whether a settings update is occuring (cleared - occuring, set - not occurring)
			settings_update_lock
				multiprocessing.Lock - allows only one process to update settings at a time (prevents semaphore acquisition deadlock)

	'''

	# query current settings on server
	response = requests.get("{}/devices/{}".format(config.get("server"), config.get("device_id")))
	response_data = response.json()
	server_setting_id = response_data["settings"]["settingsId"]

	# update settings if necessary
	if not server_setting_id == config.get("settings_id"):

		# update active settings
		settings.update_settings(
			config,
			settings_dictionary,
			json.loads(response_data["settings"]["properties"]), server_setting_id,
			threads_ready_to_update, settings_update_event, settings_update_lock
		)
		
