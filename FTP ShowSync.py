import threading, time
from ftplib import FTP
import configparser
from os.path import exists
import re
import os
import datetime

config = configparser.ConfigParser()
config.read('config.ini')
ftp_server = config['Config']['ftp_server']
port = config['Config']['port']
user = config['Config']['user']
password = config['Config']['password']
local_dir = config['Config']['local_dir']
remote_dir = config['Config']['remote_dir']
only_log_downloads = config['Config']['only_log_downloads']
delay_m = float(config['Config']['delay_m'])
global saved_latest_modified
saved_latest_modified = config['Config']['latest_modified']

def file_append(this_file,text):
	file = open(this_file, 'a+', encoding="utf8")
	file.write(text + '\n')
	file.close()

def log(text):
	# Skip if not download text when using only_log_downloads
	if (only_log_downloads) and ('download' not in text.lower() and 'running' not in text.lower()):
		return
	dateTimeObj = datetime.datetime.now()
	timestampStr = dateTimeObj.strftime("%d/%b/%Y %H:%M:%S")
	print('{}\t{}'.format(timestampStr, text))
	file_append('logs.log', '{}\t{}'.format(timestampStr, text))
	return


def Timer():
	next_call = time.time()
	while True:
		log('---------------- Running FTP Show Sync ----------------')
		if only_log_downloads:
			log('Checking every 30 minutes, only logging new downloads.')
		ftp_sync()
		next_call = next_call+(delay_m*60);
		log('Finished sync, will re-check in {} minutes.'.format(round((next_call-time.time())/60), 0))
		time.sleep(next_call - time.time())

def ftp_sync():
	global saved_latest_modified
	log(ftp_server)
	ftp = FTP(ftp_server)
	ftp.login(user, password)
	ftp.cwd(remote_dir)
	log(remote_dir)
	main_folders = list(ftp.mlsd())
	main_folders.sort(key = lambda entry: entry[1]['modify'], reverse = True)
	latest_modified = 0
	count = 0
	for folder in main_folders:
		count += 1
		# Skip if not a folder (no size)
		if folder[1].get('size'):
			continue
		# Save first folder's modified time (save to ini file at end)
		if latest_modified == 0:
			latest_modified = folder[1]['modify']

		# If modify time is less than last saved_latest_modified then break
		if float(folder[1]['modify']) <= float(saved_latest_modified):
			log('Up to date, skipping further checks.')
			break

		# Check if matching local folder exists, or skip it
		if not exists(local_dir + '\\' + folder[0]):
			log('Failed to find matching local folder: /' + folder[0] + '/, skipping.')
			continue

		#Otherwise go into the folder, and start checking files
		log('Checking folder: /' + folder[0] + '/')
		show_folder = folder[0]
		ftp.cwd(folder[0])
		file_list = list(ftp.mlsd())
		file_list.sort(key = lambda entry: entry[1]['modify'], reverse = True)
		for file in file_list:
			season_folder = ''
			# break if before save_latest_modified
			if float(file[1]['modify']) <= float(saved_latest_modified):
				break
			# If it's an mkv, try match if it exists locally
			if '.mkv' in file[0]:
				this_file = file[0]
				if file_exist_check(this_file, show_folder) == 0:
					download_file(ftp, file[0], show_folder, remote_dir, local_dir)

			# If it's a folder then let's check inside it
			if not file[1].get('size') and file[0].lower() != 'screens':
				log('Checking subfolder: /' + file[0] + '/')
				ftp.cwd(file[0])
				subfile_list = list(ftp.mlsd())
				subfile_list.sort(key = lambda entry: entry[1]['modify'], reverse = True)
				for subfile in subfile_list:
					season_folder = ''
					# break if before save_latest_modified
					if float(subfile[1]['modify']) < float(saved_latest_modified):
						break
					# If it's an mkv and doesn't exist then download it
					if '.mkv' in subfile[0]:
						this_file = subfile[0]
						if file_exist_check(this_file, show_folder) == 0:
							download_file(ftp, this_file, show_folder, remote_dir, local_dir)
				#Go back up out of subdirectory
				ftp.cwd("../")

		# Go back up to main folder directory
		ftp.cwd("../")

		# If no latest modified then break after third folder
		if int(saved_latest_modified) == 0 and count == 2:
			break

	# Save the latest_modified to the ini file
	config['Config']['latest_modified'] = latest_modified
	with open('config.ini', 'w') as configfile:
		config.write(configfile)
	log('Saved latest modified time: ' + latest_modified)
	saved_latest_modified = latest_modified
	return

def file_exist_check(file, show_folder):
	already_exists = 0
	log('\tFound new remote file: ' + file)
	# Check if exists in local folder
	if exists(local_dir + '\\' + show_folder + '\\' + file):
		already_exists = 1
	# Otherwise check if in season folder
	if already_exists == 0:
		season = re.findall(r"(?:s|season)(\d{2})(?:e|x|episode|\n)(\d{2})", file, re.I)
		for s in season:
			if s[0][0] == '0':
				if exists(local_dir + '\\' + show_folder + '\\S' + s[0].strip('0') + '\\' + file):
					already_exists = 1
					season_folder = 'S' + s[0].strip('0')
				if exists(local_dir + '\\' + show_folder + '\\Season' + s[0].strip('0') + '\\' + file):
					already_exists = 1
					season_folder = 'Season' + s[0].strip('0')
				if exists(local_dir + '\\' + show_folder + '\\Season ' + s[0].strip('0') + '\\' + file):
					already_exists = 1
					season_folder = 'Season ' + s[0].strip('0')
			if exists(local_dir + '\\' + show_folder + '\\Season' + s[0] + '\\' + file):
				already_exists = 1
				season_folder = 'Season' + s[0]
			if exists(local_dir + '\\' + show_folder + '\\Season ' + s[0] + '\\' + file):
				already_exists = 1
				season_folder = 'Season ' + s[0]
	if already_exists:
		log('\tAlready exists locally.')
	return(already_exists)

def download_file(ftp, file, show_folder, remote_dir, local_dir):
	# Check folder for the show exists
	if exists(local_dir + '\\' + show_folder):

		# Check for a season folder first
		season_folder = ''
		season = re.findall(r"(?:s|season)(\d{2})(?:e|x|episode|\n)(\d{2})", file, re.I)
		for s in season:
			if s[0][0] == '0':
				if exists(local_dir + '\\' + show_folder + '\\Season ' + s[0].strip('0')):
					season_folder = 'Season ' + s[0].strip('0')
					break
				if exists(local_dir + '\\' + show_folder + '\\Season ' + s[0].strip('0')):
					season_folder = 'Season' + s[0].strip('0')
					break
			if exists(local_dir + '\\' + show_folder + '\\Season ' + s[0]):
				season_folder = 'Season ' + s[0]
				break
			if exists(local_dir + '\\' + show_folder + '\\Season ' + s[0]):
				season_folder = 'Season' + s[0]
				break
		if season_folder != '':
			log('\t<--- DOWNLOADING to "{}\\{}\\{}\\"'.format(local_dir, show_folder, season_folder))
			try:
				ftp.retrbinary("RETR " + file, open(local_dir + '\\' + show_folder + '\\' + season_folder + '\\' + file, 'wb').write)
				log('\tDOWNLOAD COMPLETE.')
			except Exception as e:
				log(e)
				log("\tError downloading file.")
			return

		# Otherwise just put it in the show folder
		log('\t<--- DOWNLOADING to "{}\\{}\\"'.format(local_dir, show_folder))
		try:
			ftp.retrbinary("RETR " + file, open(local_dir + '\\' + show_folder + '\\' + file, 'wb').write)
			log('\tDOWNLOAD COMPLETE.')
		except:
			log("\tError downloading file.")
		return
	log('\tCould not find local show folder: ' + show_folder)
	return

timerThread = threading.Thread(target=Timer)
timerThread.start() 