import threading, time
from ftplib import FTP
import configparser
from os.path import exists
import re
import os
import datetime
import sys

import psutil
import traceback

#filename = 'Slow.Horses.S01E01.Failures.Contagious.1080p.WEBRip.DDP5.1.H265-d3g'
#filename = 'my.hero.academia.s01e13 [English Dubbed] 720p x264 ~ARIZONE.mp4'
#this_s, this_e = re.findall(r"(?:s|season)(\d{2})(?:e|x|episode|\n)(\d{2})", filename, re.I)[0]
#print(this_s, this_e)


from progressbar import AnimatedMarker, Bar, BouncingBar, Counter, ETA, \
	AdaptiveETA, FileTransferSpeed, FormatLabel, Percentage, \
	ProgressBar, ReverseBar, RotatingMarker, \
	SimpleProgress, Timer, UnknownLength

def file_append(this_file, text):
	file = open(this_file, 'a+', encoding="utf8")
	file.write(text + '\n')
	file.close()
	return

def log(text):
	dateTimeObj = datetime.datetime.now()
	timestampStr = dateTimeObj.strftime("%d/%b/%Y %H:%M:%S")
	if only_log_downloads == '0':
		print(f'{timestampStr} {text}')
	# Skip if not download text when using only_log_downloads
	contains_list = ['download', 'already exists', 'found ', 'ERROR', 'failed']
	if only_log_downloads == '1' and any(contains.lower() in text.lower() for contains in contains_list):
		print(f'{timestampStr} {text}')
		file_append('download_logs.log', f'{timestampStr} {text}')
	file_append('logs.log', f'{timestampStr} {text}')
	return

def log_end(text, end):
	dateTimeObj = datetime.datetime.now()
	timestampStr = dateTimeObj.strftime("%d/%b/%Y %H:%M:%S")
	print(f'\r{timestampStr} {text}', end)
	file = open('logs.log', 'a+', encoding="utf8")
	file.write(f'{timestampStr} {text}')
	file.close()
	return

# WHEN IT SYNCS
def ftp_sync(config):
	global saved_latest_modified

	def show_folder_check(folder):
		# Check each local dir for folder
		for local_dir in cfg["local_dirs"]:
			this_dir = local_dir + '\\' + folder
			if exists(this_dir):
				log(f' - Found existing local folder: {this_dir}')
				return(folder)

		# If still not exist, then make it in the first folder
		if cfg_check("create_show_folder"):
			os.mkdir(this_dir)
			log(f' - Created new folder: {this_dir}')
			return(folder)

		log(' - Failed to find matching local folder: /' + folder + ', skipping.')
		return 0

	def check_folder(folder, saved_latest_modified):
		try:
			contents = list(ftp.mlsd(folder))
		except Exception:
			log(f"Failed to list folder: {folder}")
			log(traceback.format_exc())
			return [], []

		contents.sort(key=lambda e: e[1].get('modify', ''), reverse=True)
		files = []
		folders = []
		status = ''

		for name, facts in contents:
			try:
				modify = facts.get('modify')
				if modify and modify <= saved_latest_modified:
					log(f' - "{name}" older than saved time ({modify} <= {saved_latest_modified}), breaking')
					status = 'break'
					break

				entry_type = facts.get('type')

				# Directories
				if entry_type == 'dir':
					folders.append(f'{folder}/{name}')
					continue

				# Files
				if entry_type == 'file':
					if cfg["filetypes"] and not any(name.lower().endswith(ft) for ft in cfg["filetypes"]):
						continue

					size_bytes = int(facts.get('size', 0))
					size_mb = round(size_bytes / (1024 * 1024))

					if cfg_check("min_file_size_mb") and size_mb < int(cfg["min_file_size_mb"]):
						continue

					log(f' - Added new file "{name}" ({size_mb} MB)')
					files.append(f'{folder}/{name} ({size_mb})')

			except Exception as e:
				log(f'ERROR: {e}')
				log(traceback.print_exc())
				status = 'ERROR'
				return files, folders, status

		return files, folders, status



	def check_for_new_files(folder, saved_latest_modified, new_latest_modified, count):
		try:
			show_folders = list(ftp.mlsd())
			show_folders.sort(key = lambda entry: entry[1]['modify'], reverse = True)

			for show_folder in show_folders:
				new_files = []
				status = ''

				# Save first folder's modified time (save to ini file at end)
				if new_latest_modified == 0:
					new_latest_modified = show_folder[1]['modify']
					if str(new_latest_modified) != str(saved_latest_modified):
						log('Got new latest modified time: ' + str(new_latest_modified))

				# If no saved time then get the latest modified time and return
				if int(saved_latest_modified) == 0:
					log('Got initial latest time: ' + str(new_latest_modified))
					return new_latest_modified

				# If negative then only check that number of folders then break and have newest time
				if int(saved_latest_modified) < 0 and count == int(str(saved_latest_modified.replace('-',''))):
					return new_latest_modified

				if float(show_folder[1]['modify']) <= float(saved_latest_modified):
					log(f'Folder [{show_folder[0]}] older than last check, finishing.')
					#print(f"{float(show_folder[1]['modify'])} <= {float(saved_latest_modified)}")
					return new_latest_modified

				# Check show folder first
				this_dir = show_folder[0]
				log(f'Checking folder [{show_folder[0]}]')
				new_files, new_folders, status = check_folder(show_folder[0], saved_latest_modified)
				#print('new_folders: ' + str(new_folders))
				if new_files:
					new_files.extend(new_files)

				# Loop subfolders until no new_folders
				while new_folders:
					subfolders = new_folders
					new_folders = []
					if status in ['break', 'ERROR']:
						break
					for subfolder in subfolders:
						log(f' - Checking subfolder [{subfolder}]')
						found_files, found_folders, status = check_folder(subfolder, saved_latest_modified)
						if found_files:
							new_files.extend(found_files)
						if found_folders:
							new_folders.extend(found_folders)

				# Download new files
				if new_files:
					max_count = len(new_files)
					log(f' - Checking {len(new_files)} new [{show_folder[0]}] file(s)...')

					# If searching through folders
					if cfg_check("no_folders"):
						log(f' - cfg "no_folders" set, no local subfolders.')
						show_folder_exists = 0
					else:
						# Check if the directory exists, otherwise make it
						show_folder_exists = show_folder_check(show_folder[0])
						if not show_folder_exists:
							log(f' - No local folder [{show_folder[0]}] exists or created, skipping.')
							continue

					# Download files
					new_files.sort()
					count = 0
					for this_file in new_files:
						count += 1
						log(f' - New file: {this_file.split("/")[-1]}')
						status = download_file(ftp, this_file, show_folder_exists, cfg["local_dirs"][0], count, max_count)

						if status == 'ERROR':
							return(status)

				if not new_files:
					log(f' - No new files found in [{show_folder[0]}]')

			return new_latest_modified

		except Exception as e:
			log(f'ERROR (L{sys.exc_info()[-1].tb_lineno}): {e} ')
			log(traceback.print_exc())
			return

	# FROM HERE
	try:
		last_ftp_server = ""
		for section in config.sections():
			if section == 'Config' or config[section].get('enabled', '1') == '0':
				continue
			global cfg
			cfg = dict(config[section])
			# Make these into ists
			cfg["local_dirs"] = config[section]['local_dirs'].replace(' ,',',').split(',')
			cfg["filetypes"] = config[section]['filetypes'].replace(' ,',',').split(',')
			global saved_latest_modified
			saved_latest_modified = config[section]['latest_modified']
			if saved_latest_modified == 'None':
				saved_latest_modified = 0

			# Connect to the server
			if cfg["ftp_server"] != last_ftp_server:
				# Disconnect form the last one
				if last_ftp_server:
					ftp.quit()
					log(f'Disconnected.')
				ftp = FTP(cfg["ftp_server"])
				ftp.login(cfg["user"], cfg["password"])
				log(f'------------ Connected to {cfg["ftp_server"]} [{section}] ------------ ')
			else:
				log(f'------------ Checking {cfg["ftp_server"]} [{section}] ------------ ')
			last_ftp_server = cfg["ftp_server"]
			ftp.cwd(cfg["remote_dir"])
			log(f'Checking {cfg["remote_dir"]}, saved_latest_modified {saved_latest_modified}')

			global new_latest_modified
			new_latest_modified = 0
			count = 0


			# get parent and child folders in directory
			new_latest_modified = check_for_new_files(cfg["remote_dir"], saved_latest_modified, new_latest_modified, count)

			if new_latest_modified == 'ERROR':
				return('ERROR')

			#print('153: new_latest_modified: ' + str(new_latest_modified))

			# Save the latest_modified to the ini file
			if str(new_latest_modified) != str(saved_latest_modified):
				config[section]['latest_modified'] = str(new_latest_modified)
				with open('config.ini', 'w') as configfile:
					config.write(configfile)
				log('Saved latest modified time: ' + str(new_latest_modified))
				saved_latest_modified = new_latest_modified

		ftp.quit()
		log(f'Disconnected.')

	except Exception as e:
		log(f'ERROR Failed to connect: {e}')
		log(traceback.print_exc())
		return('ERROR')

	return


def download_file(ftp, file, show_folder, local_dir, count, max_count):

	def file_write(data):
		this_file.write(data) 
		global pbar
		pbar += len(data)

	try:
		file_size_mb = 0
		filename = str(file).split('/')[-1]
		filename, file_size_mb = filename.rsplit(' (', 1)
		file_size_mb = file_size_mb.replace(')', '')

		if ' (' in file:
			file = file.rsplit(' (', 1)[0]

		# Skip if the file already exists
		if file_exist_check(file, show_folder, local_dir):
			log(f'   File already exists: {file}')
			return

		# No folders for Movies
		if cfg_check("no_folders"):
			local_loc = local_dir

		# Or for TV Shows / Anime
		else:
			local_loc = local_dir + '\\' + show_folder
			# Check folder for the show exists
			if exists(local_loc):

				# Check if episode exists already in the main directory
				if cfg_check("check_if_episode_exists_already"):
					if check_episode_exists(file, show_folder, local_dir):
						return

				# Check for a season folder first
				season, episode = get_season_episode(file)

				#season = re.findall(r"(?:s|season)(\d{2})(?:e|x|episode|\n)(\d{2})", file, re.I)
				if not season:
					log(f'ERROR: Could not find season number for file: {file}')
					return

				s = 0
				season_folder = ''
				for s in season:
					s = s.lstrip('0')
					if exists(local_dir + '\\' + show_folder + '\\Season ' + s):
						season_folder = f'Season {s}'
						break
					if exists(local_dir + '\\' + show_folder + '\\Season' + s):
						season_folder = f'Season{s}'
						break
					if exists(local_dir + '\\' + show_folder + '\\Season 0' + s):
						season_folder = f'Season 0{s}'
						break

				# If it finds a season folder, use that
				if season_folder != '':
					local_loc = f'{local_dir}\\{show_folder}\\{season_folder}\\{filename}'
					# Check episode doesn't already exist
					if cfg_check("check_if_episode_exists_already"):
						if check_episode_exists(file, show_folder, local_dir):
							return

				else:
					# Put it in a new season folder
					if cfg_check("create_season_folder") and s:
						log(f'Created "{show_folder}\\Season {s}" folder')
						os.mkdir(f'{local_dir}\\{show_folder}\\Season {s}')
						local_loc = f'{local_dir}\\{show_folder}\\Season {s}\\{filename}'
					# Otherwise just put it in the show folder
					else:
						local_loc = f'{local_dir}\\{show_folder}\\{filename}'

		# Check the drive isn't full
		hdd_free_mb = psutil.disk_usage(local_dir).free / 1024 / 1024
		if int(file_size_mb) > int(hdd_free_mb):
			log(f'ERROR: Drive out of space (file: {file_size_mb} MB, drive: {hdd_free_mb} MB')
			return('ERROR')

		if int(file_size_mb) > 1000:
			file_size = str(round(int(file_size_mb) / 1024, 1)) + 'GB'
		else:
			file_size = str(file_size_mb) + 'MB'

		download_text = f' ({count}/{max_count}) Downloading: {local_loc} ({file_size})'
		log(download_text)

		# Download bar
		ftp.voidcmd('TYPE I')
		size = ftp.size(file)
		widgets = [' ', Percentage(), ' ', Bar(marker='#',left='[',right=']'),' ', ETA(), ' ', FileTransferSpeed()]
		global pbar
		pbar = ProgressBar(widgets=widgets, maxval=size)
		pbar.start()

		# Download
		this_file = open(local_loc, 'wb')
		ftp.retrbinary("RETR " + file, file_write)
		#log_end(f'{download_text} [DONE]', '\r')
		pbar.finish()
		return

	except Exception as e:
		log(f'ERROR (L{sys.exc_info()[-1].tb_lineno}): {e} ')
		log(traceback.print_exc())
		return

	log('Could not find local show folder: ' + show_folder)
	return

def cfg_check(setting):
	if setting not in cfg:
		return(0)
	if not cfg[setting]:
		return(0)
	return(1)

def file_exist_check(file, sub_folder, local_dir):
	filename = str(file).split('/')[-1]
	already_exists = 0

	if not sub_folder:
		for local_dir in cfg["local_dirs"]:
			if exists(local_dir + '\\' + file):
				return(1)
		return(0)

	# Check if exists in local folder
	if exists(local_dir + '\\' + sub_folder + '\\' + filename):
		return(1)

	season, file_episode = get_season_episode(file)

	# season = re.findall(r"(?:s|season)(\d{2})(?:e|x|episode|\n)(\d{2})", file, re.I)
	for s in season:
		s = s.lstrip('0')
		if exists(f'{local_dir}\\{sub_folder}\\Season {s}\\{filename}'):
			return(1)
		if exists(f'{local_dir}\\{sub_folder}\\Season {s}\\{filename}'):
			return(1)
		if exists(f'{local_dir}\\{sub_folder}\\Season 0{s}\\{filename}'):
			return(1)
	return(0)


def check_episode_exists(file, show_folder, local_dir):
	try:
		if '/' in file:
			new_file = str(file).split('/')[-1]

		file_season, file_episode = get_season_episode(file)

		# Error for the file
		if not file_episode:
			log(f'ERROR: Could not get episode number for file: {new_file}')
			return(0)

		if file_episode != 0:
			for (dirpath, dirnames, filenames) in os.walk(local_dir + '\\' + show_folder):
				for file in filenames:
					try:
						season, episode = get_season_episode(file)
						# If can't get an episode number
						if episode == 0 and file_episode == 0:
							if new_file == file:
								log(f'   Episode already exists ({new_file}), skipping.')
								return(file)
						# If the season and episode match
						elif f'{season}{episode}' == f'{file_season}{file_episode}':
							# If there's an overwrite on the new file, then delete the current one
							if cfg_check("overwrite_if_new_contains") and new_file:
								if any(x in new_file for x in cfg["overwrite_if_new_contains"].replace(' ','').split(',')): # new file has overwrite text
									if any(x in filename for x in cfg["overwrite_if_new_contains"].replace(' ','').split(',')): # current file doesn't have overwrite
										log(f'   File of same episode exists ({file}), but new file ({new_file}) contains overwrite.')
										os.remove(os.path.join(dirpath, filename))
										return(0)

							log(f'   Episode already exists (S{season}{episode}), skipping.')
							return(file)
					except:
						continue

	except Exception as e:
		log(f'ERROR (L{sys.exc_info()[-1].tb_lineno}): {e} ')
		log(traceback.print_exc())

	return(0)

def get_season_episode(this_filename):
	file_season = 0
	file_episode = 0

	try:
		# Regex to get season and episode
		matches = re.findall(r"([Ss]?)(\d{1,2})([xXeE\.\-])(\d{1,2})", this_filename, re.I)[0]
		file_season = matches[1]
		file_episode = matches[3]
	except:
		pass

	# If it failed to get them then default to Season 1 and get episode number
	if file_season == 0 or file_episode == 0:
		file_season = '01'
		ep_match = re.findall(r'(\d{1,3})', this_filename)
		file_episode = ep_match[1] if ep_match else 0

	return(file_season, file_episode)


def main():
	next_call = time.time()
	config = configparser.ConfigParser()
	config.read('config.ini')
	delay_m = float(config['Config']['delay_m'])
	global only_log_downloads
	only_log_downloads = config['Config']['only_log_downloads']
	if only_log_downloads == '1':
		log('Checking every 30 minutes, only logging new downloads.')

	while True:
		status = ftp_sync(config)
		if status == 'ERROR':
			break
		next_call = next_call+(delay_m*60)
		next_call_delta = max(0, round((next_call-time.time())/60), 0)
		if next_call != 0:
			log(f'Re-checking in {next_call_delta} minutes.')
			time.sleep(next_call_delta*60)

	return

if __name__ == "__main__":
	main()