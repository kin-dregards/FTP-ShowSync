import re

def main():
	this_filename = "Stranger.Things.4x09.Chapter.Nine.The.Piggyback.1080p.WEBRip.DDP5.1.Atmos.H265-d3g.mkv"
	matches = re.findall(r"([Ss]?)(\d{1,2})([xXeE\.\-])(\d{1,2})", this_filename, re.I)[0]
	print(matches)
	file_season = matches[1]
	file_episode = matches[3]
	print(file_season, file_episode)

if __name__ == "__main__":
	main()