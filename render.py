#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# KINDLE WEATHER DASHBOARD PILLOW RENDERER (CLONED LAYOUT)
# ==============================================================================
# Enforces Unix (LF) line endings. Python 2/3 compatible.
# ==============================================================================

import os
import sys
import json
import math
import datetime
import socket
import time
socket.setdefaulttimeout(15)

try:
	import urllib.request as urllib2
except ImportError:
	import urllib2

try:
	import urllib.parse as urllib_parse
except ImportError:
	import urllib as urllib_parse

from PIL import Image, ImageDraw, ImageFont

# ------------------------------------------------------------------------------
# CONSTANTS & DIRECTORIES
# ------------------------------------------------------------------------------
EXT_DIR = "/mnt/us/extensions/weather-station"
if not os.path.exists(EXT_DIR):
	EXT_DIR = "."  # Fallback for local testing

OUTPUT_PATH = "/tmp/output.png"
if not os.path.exists("/tmp"):
	OUTPUT_PATH = "output.png"  # Fallback for local testing

# ------------------------------------------------------------------------------
# FONT LOADER HELPER
# ------------------------------------------------------------------------------
def load_system_font(font_names, size):
	paths = [
		"/usr/java/lib/fonts/",
		"/var/local/font/mnt/zh-Hans_font/fonts/",
		"/usr/lib/fonts/",
		"/system/fonts/",
		os.path.join(EXT_DIR, "fonts"),
		"C:\\Windows\\Fonts\\"  # Local Windows test path
	]
	for name in font_names:
		for path in paths:
			full_path = os.path.join(path, name)
			if os.path.exists(full_path):
				try:
					return ImageFont.truetype(full_path, size)
				except Exception:
					pass
	# Fallback to PIL default if no font found
	return ImageFont.load_default()

# Load specific typographic styles
FONT_CHINESE = lambda size: load_system_font(["MYingHeiSMedium.ttf", "MYingHeiSBold.ttf", "STSongMedium.ttf", "code2000.ttf", "STKaiMedium.ttf", "arial.ttf"], size)
FONT_SERIF = lambda size: load_system_font(["Caecilia_LT_65_Medium.ttf", "Baskerville-Regular.ttf", "Palatino-Regular.ttf", "times.ttf"], size)
FONT_SANS = lambda size: load_system_font(["Helvetica_LT_65_Medium.ttf", "Futura-Medium.ttf", "Helvetica.ttf", "arial.ttf"], size)

# ------------------------------------------------------------------------------
# SEVEN-SEGMENT LCD DISPLAY DRAWING LOGIC (NO FONT FILE REQUIRED)
# ------------------------------------------------------------------------------
def draw_digit_7seg(draw, x, y, w, h, char, thickness=12):
	# Segments Layout:
	#      A
	#    F   B
	#      G
	#    E   C
	#      D
	
	# Chamfered segment coordinates
	segments = {
		'A': [(x + thickness, y), (x + w - thickness, y), (x + w - 2*thickness, y + thickness), (x + 2*thickness, y + thickness)],
		'B': [(x + w, y + thickness), (x + w, y + h//2 - thickness//2), (x + w - thickness, y + h//2 - thickness//2), (x + w - thickness, y + 2*thickness)],
		'C': [(x + w, y + h//2 + thickness//2), (x + w, y + h - thickness), (x + w - thickness, y + h - 2*thickness), (x + w - thickness, y + h//2 + thickness//2)],
		'D': [(x + thickness, y + h), (x + w - thickness, y + h), (x + w - 2*thickness, y + h - thickness), (x + 2*thickness, y + h - thickness)],
		'E': [(x, y + h//2 + thickness//2), (x, y + h - thickness), (x + thickness, y + h - 2*thickness), (x + thickness, y + h//2 + thickness//2)],
		'F': [(x, y + thickness), (x, y + h//2 - thickness//2), (x + thickness, y + h//2 - thickness//2), (x + thickness, y + 2*thickness)],
		'G': [(x + thickness, y + h//2 - thickness//2), (x + w - thickness, y + h//2 - thickness//2), (x + w - 2*thickness, y + h//2 + thickness//2), (x + 2*thickness, y + h//2 + thickness//2)]
	}
	
	char_map = {
		'0': ['A', 'B', 'C', 'D', 'E', 'F'],
		'1': ['B', 'C'],
		'2': ['A', 'B', 'G', 'E', 'D'],
		'3': ['A', 'B', 'G', 'C', 'D'],
		'4': ['F', 'G', 'B', 'C'],
		'5': ['A', 'F', 'G', 'C', 'D'],
		'6': ['A', 'F', 'G', 'E', 'D', 'C'],
		'7': ['A', 'B', 'C'],
		'8': ['A', 'B', 'C', 'D', 'E', 'F', 'G'],
		'9': ['A', 'B', 'C', 'D', 'F', 'G'],
		'-': ['G']
	}
	
	active_segs = char_map.get(char, [])
	for seg_name in active_segs:
		draw.polygon(segments[seg_name], fill=0)

def draw_string_7seg(draw, x, y, string, char_w, char_h, space=15, thickness=12):
	curr_x = x
	for char in string:
		if char == ':':
			# Draw colon dots: 7 seconds shown, 3 seconds hidden
			show_colon = (datetime.datetime.now().second % 10) < 7
			dot_size = thickness
			if show_colon:
				draw.rectangle([curr_x + space, y + char_h//3 - dot_size//2, curr_x + space + dot_size, y + char_h//3 + dot_size//2], fill=0)
				draw.rectangle([curr_x + space, y + 2*char_h//3 - dot_size//2, curr_x + space + dot_size, y + 2*char_h//3 + dot_size//2], fill=0)
			curr_x += dot_size + 2 * space
		elif char == ' ':
			curr_x += char_w + space
		else:
			draw_digit_7seg(draw, curr_x, y, char_w, char_h, char, thickness)
			curr_x += char_w + space

# ------------------------------------------------------------------------------
# Minimalist Vector Weather Icon Drawing Logic (Fallback if no PNG icons found)
# ------------------------------------------------------------------------------
def draw_sun_icon(draw, center, size):
	x, y = center
	r = size // 2
	draw.ellipse([x - r//2, y - r//2, x + r//2, y + r//2], outline=0, width=4)
	for i in range(8):
		angle = i * (math.pi / 4)
		x1 = x + int((r//2 + 4) * math.cos(angle))
		y1 = y + int((r//2 + 4) * math.sin(angle))
		x2 = x + int((r - 2) * math.cos(angle))
		y2 = y + int((r - 2) * math.sin(angle))
		draw.line([x1, y1, x2, y2], fill=0, width=3)

def draw_clouds_icon(draw, center, size):
	x, y = center
	r = size // 2
	# Back cloud (smaller)
	bx = x + r//3
	by = y - r//4
	br = int(r * 0.7)
	draw.ellipse([bx - br//2, by - br//4, bx - br//6, by + br//4], fill=255, outline=0, width=4)
	draw.ellipse([bx - br//3, by - br//2, bx + br//3, by + br//6], fill=255, outline=0, width=4)
	draw.ellipse([bx + br//6, by - br//4, bx + br//2, by + br//4], fill=255, outline=0, width=4)
	draw.rectangle([bx - br//2 + 2, by, bx + br//2 - 2, by + br//4], fill=255)
	draw.line([bx - br//2, by + br//4, bx + br//2, by + br//4], fill=0, width=4)
	# Front cloud (larger)
	draw.ellipse([x - r//2, y - r//4, x - r//6, y + r//4], fill=255, outline=0, width=4)
	draw.ellipse([x - r//3, y - r//2, x + r//3, y + r//6], fill=255, outline=0, width=4)
	draw.ellipse([x + r//6, y - r//4, x + r//2, y + r//4], fill=255, outline=0, width=4)
	draw.rectangle([x - r//2 + 2, y, x + r//2 - 2, y + r//4], fill=255)
	draw.line([x - r//2, y + r//4, x + r//2, y + r//4], fill=0, width=4)

def draw_sunny_cloudy_icon(draw, center, size):
	x, y = center
	r = size // 2
	# Sun behind (top-right)
	sx = x + r//3
	sy = y - r//3
	sr = int(r * 0.7)
	draw.ellipse([sx - sr//2, sy - sr//2, sx + sr//2, sy + sr//2], outline=0, width=3)
	for i in range(8):
		angle = i * (math.pi / 4)
		x1 = sx + int((sr//2 + 2) * math.cos(angle))
		y1 = sy + int((sr//2 + 2) * math.sin(angle))
		x2 = sx + int((sr - 2) * math.cos(angle))
		y2 = sy + int((sr - 2) * math.sin(angle))
		draw.line([x1, y1, x2, y2], fill=0, width=2)
	# Cloud in front (centered-left)
	cx = x - 5
	cy = y + 5
	draw.ellipse([cx - r//2, cy - r//4, cx - r//6, cy + r//4], fill=255, outline=0, width=4)
	draw.ellipse([cx - r//3, cy - r//2, cx + r//3, cy + r//6], fill=255, outline=0, width=4)
	draw.ellipse([cx + r//6, cy - r//4, cx + r//2, cy + r//4], fill=255, outline=0, width=4)
	draw.rectangle([cx - r//2 + 2, cy, cx + r//2 - 2, cy + r//4], fill=255)
	draw.line([cx - r//2, cy + r//4, cx + r//2, cy + r//4], fill=0, width=4)

def draw_rainy_icon(draw, center, size):
	x, y = center
	r = size // 2
	cy = y - 10
	draw.ellipse([x - r//2, cy - r//4, x - r//6, cy + r//4], fill=255, outline=0, width=4)
	draw.ellipse([x - r//3, cy - r//2, x + r//3, cy + r//6], fill=255, outline=0, width=4)
	draw.ellipse([x + r//6, cy - r//4, x + r//2, cy + r//4], fill=255, outline=0, width=4)
	draw.rectangle([x - r//2 + 2, cy, x + r//2 - 2, cy + r//4], fill=255)
	draw.line([x - r//2, cy + r//4, x + r//2, cy + r//4], fill=0, width=4)
	# Rain drops
	draw.line([x - r//3, cy + r//4 + 8, x - r//3 - 3, cy + r//4 + 18], fill=0, width=3)
	draw.line([x, cy + r//4 + 8, x - 3, cy + r//4 + 18], fill=0, width=3)
	draw.line([x + r//3, cy + r//4 + 8, x + r//3 - 3, cy + r//4 + 18], fill=0, width=3)

def draw_snowy_icon(draw, center, size):
	x, y = center
	r = size // 2
	cy = y - 10
	draw.ellipse([x - r//2, cy - r//4, x - r//6, cy + r//4], fill=255, outline=0, width=4)
	draw.ellipse([x - r//3, cy - r//2, x + r//3, cy + r//6], fill=255, outline=0, width=4)
	draw.ellipse([x + r//6, cy - r//4, x + r//2, cy + r//4], fill=255, outline=0, width=4)
	draw.rectangle([x - r//2 + 2, cy, x + r//2 - 2, cy + r//4], fill=255)
	draw.line([x - r//2, cy + r//4, x + r//2, cy + r//4], fill=0, width=4)
	# Snowflakes (dots)
	draw.ellipse([x - r//3 - 2, cy + r//4 + 10, x - r//3 + 2, cy + r//4 + 14], fill=0)
	draw.ellipse([x - 2, cy + r//4 + 10, x + 2, cy + r//4 + 14], fill=0)
	draw.ellipse([x + r//3 - 2, cy + r//4 + 10, x + r//3 + 2, cy + r//4 + 14], fill=0)

def draw_weather_icon(draw, center, size, state):
	if state == "Sunny":
		draw_sun_icon(draw, center, size)
	elif state == "SunnyCloudy":
		draw_sunny_cloudy_icon(draw, center, size)
	elif state == "Cloudy":
		draw_clouds_icon(draw, center, size)
	elif state == "Rainy":
		draw_rainy_icon(draw, center, size)
	elif state == "Snowy":
		draw_snowy_icon(draw, center, size)
	else:
		draw_clouds_icon(draw, center, size)

# Map OpenWeatherMap ID to general categories
def get_weather_state(weather_id):
	if 200 <= weather_id < 600:
		return "Rainy"
	elif 600 <= weather_id < 700:
		return "Snowy"
	elif weather_id == 800:
		return "Sunny"
	elif weather_id in [801, 802]:
		return "SunnyCloudy"
	else:
		return "Cloudy"

# Custom Sun Graphic for Sunrise
def draw_sunrise_graphic(draw, center, size):
	x, y = center
	r = size // 2
	draw.line([x - r, y + 4, x + r, y + 4], fill=0, width=2)
	draw.arc([x - r//2, y - r//2 + 4, x + r//2, y + r//2 + 4], start=180, end=360, fill=0, width=2)
	draw.line([x, y - r//2, x, y - r], fill=0, width=2)
	draw.line([x - r//3, y - r//3, x - r//2 - 2, y - r//2 - 2], fill=0, width=2)
	draw.line([x + r//3, y - r//3, x + r//2 + 2, y - r//2 - 2], fill=0, width=2)

# Custom Moon/Sun Graphic for Sunset
def draw_sunset_graphic(draw, center, size):
	x, y = center
	r = size // 2
	draw.line([x - r, y + 4, x + r, y + 4], fill=0, width=2)
	draw.arc([x - r//2, y - r//3 + 4, x + r//2, y + 2*r//3 + 4], start=180, end=360, fill=0, width=2)
	draw.line([x, y - r//4, x, y - r//2], fill=0, width=2)
	draw.line([x - r//3, y - r//6, x - r//2, y - r//3], fill=0, width=2)
	draw.line([x + r//3, y - r//6, x + r//2, y - r//3], fill=0, width=2)

# ------------------------------------------------------------------------------
# API FETCHING
# ------------------------------------------------------------------------------
def fetch_forecast(api_key, city):
	encoded_city = urllib_parse.quote(city)
	url = "https://api.openweathermap.org/data/2.5/forecast?q={0}&units=metric&appid={1}".format(encoded_city, api_key)
	
	# Bypass SSL verification for older Kindle certs
	import ssl
	try:
		context = ssl._create_unverified_context()
		response = urllib2.urlopen(url, timeout=15, context=context)
	except AttributeError:
		response = urllib2.urlopen(url, timeout=15)
		
	return json.loads(response.read().decode('utf-8'))

# ------------------------------------------------------------------------------
# RENDER PIPELINE
# ------------------------------------------------------------------------------
def main():
	if len(sys.argv) < 3:
		print("Usage: render.py <API_KEY> <CITY_NAME>")
		sys.exit(1)
		
	api_key = sys.argv[1]
	city_query = sys.argv[2]
	
	# 1. Fetch & Parse Data (with 5-minute caching mechanism)
	cache_path = "/tmp/weather_forecast.json"
	data = None
	
	if os.path.exists(cache_path):
		mtime = os.path.getmtime(cache_path)
		if time.time() - mtime < 300: # 5 minutes
			try:
				with open(cache_path, "r", encoding="utf-8") as f:
					data = json.load(f)
				print("Using cached weather forecast data.")
			except Exception:
				pass
				
	if data is None:
		try:
			data = fetch_forecast(api_key, city_query)
			with open(cache_path, "w", encoding="utf-8") as f:
				json.dump(data, f)
		except Exception as e:
			# Fallback to expired cache if API fails
			if os.path.exists(cache_path):
				try:
					with open(cache_path, "r", encoding="utf-8") as f:
						data = json.load(f)
					print("API failed, using expired cache data.")
				except Exception:
					pass
			
			if data is None:
				print("API Error: {0}".format(e))
				sys.exit(1)
				
	# Extract parameters
	timezone_offset = data["city"]["timezone"]
	city_name = data["city"]["name"]
	sunrise_ts = data["city"]["sunrise"]
	sunset_ts = data["city"]["sunset"]
	
	# Current forecast (first entry)
	current_entry = data["list"][0]
	current_temp = int(round(current_entry["main"]["temp"]))
	current_desc = current_entry["weather"][0]["description"]
	
	# Map custom weather status strings to match screenshot (Chinese characters)
	desc_mapping = {
		"clear sky": "晴",
		"few clouds": "少云",
		"scattered clouds": "多云",
		"broken clouds": "多云",
		"overcast clouds": "阴, 多云",
		"light rain": "小雨",
		"moderate rain": "中雨",
		"heavy intensity rain": "大雨",
		"snow": "雪"
	}
	current_desc_cn = desc_mapping.get(current_desc.lower(), current_desc.capitalize())
	current_state = get_weather_state(current_entry["weather"][0]["id"])
	
	# Sunrise/Sunset local times
	sunrise_dt = datetime.datetime.utcfromtimestamp(sunrise_ts + timezone_offset)
	sunset_dt = datetime.datetime.utcfromtimestamp(sunset_ts + timezone_offset)
	sunrise_str = sunrise_dt.strftime("%H:%M")
	sunset_str = sunset_dt.strftime("%H:%M")
	
	# Date/time
	now = datetime.datetime.now()
	date_str = now.strftime("%m-%d")
	time_str = now.strftime("%H:%M")
	week_num = now.isocalendar()[1]
	
	days_chinese = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
	day_of_week = days_chinese[now.weekday()]
	
	# Read orientation state
	orientation = "portrait"
	state_file = os.path.join(EXT_DIR, "orientation.state")
	if os.path.exists(state_file):
		try:
			with open(state_file, "r") as f:
				orientation = f.read().strip().lower()
		except Exception:
			pass
			
	# Read language state
	lang = "zh"
	lang_file = os.path.join(EXT_DIR, "language.state")
	if os.path.exists(lang_file):
		try:
			with open(lang_file, "r") as f:
				lang = f.read().strip().lower()
		except Exception:
			pass
			
	if orientation == "landscape":
		# 2a. Setup Image Canvas (1024x758 Grayscale Landscape)
		image = Image.new("L", (1024, 758), 255) # 255 = White
		draw = ImageDraw.Draw(image)
		
		# Weather description layout based on language
		en_desc_mapping = {
			"clear sky": "Clear Sky",
			"few clouds": "Few Clouds",
			"scattered clouds": "Scattered",
			"broken clouds": "Broken",
			"overcast clouds": "Overcast",
			"light rain": "Light Rain",
			"moderate rain": "Mod. Rain",
			"heavy intensity rain": "Heavy Rain",
			"snow": "Snow",
			"light snow": "Light Snow"
		}
		if lang == "en":
			desc_text = en_desc_mapping.get(current_desc.lower(), current_desc.capitalize())
			desc_font = FONT_SANS(44)
		else:
			desc_text = current_desc_cn
			desc_font = FONT_CHINESE(48)
			
		# SECTION 1: TOP SECTION (Y = 0 to 220)
		draw_weather_icon(draw, (120, 110), 140, current_state)
		draw.text((250, 20), desc_text, font=desc_font, fill=0)
		draw.text((250, 140), "{0}°C".format(current_temp), font=FONT_SERIF(36), fill=0)
		
		# Right City Name
		try:
			w_city = draw.textsize(city_name, font=FONT_CHINESE(48))[0]
		except AttributeError:
			l, t, r, b = draw.textbbox((0, 0), city_name, font=FONT_CHINESE(48))
			w_city = r - l
		draw.text((940 - w_city, 20), city_name, font=FONT_CHINESE(48), fill=0)
		
		# Date (Right, seven-segment format)
		draw_string_7seg(draw, 680, 95, date_str, 40, 75, space=10, thickness=8)
		
		# Divider line
		draw.line([(0, 220), (1024, 220)], fill=0, width=2)
		
		# SECTION 2: MIDDLE SECTION (Giant Real-time Clock, Y = 220 to 500)
		clock_w = 120 * 4 + 24 + 30 * 4
		clock_x_start = (1024 - clock_w) // 2
		draw_string_7seg(draw, clock_x_start, 250, time_str, 120, 220, space=30, thickness=24)
		
		# Divider line
		draw.line([(0, 500), (1024, 500)], fill=0, width=2)
		
		# SECTION 3: BOTTOM SECTION (4-column Forecast, Y = 500 to 710)
		col_width = 231
		start_x = 50
		
		for i in range(4):
			fc = data["list"][i + 1]
			fc_ts = fc["dt"]
			fc_temp = int(round(fc["main"]["temp"]))
			fc_desc_raw = fc["weather"][0]["description"]
			fc_desc_cn = desc_mapping.get(fc_desc_raw.lower(), fc_desc_raw.capitalize())
			fc_state = get_weather_state(fc["weather"][0]["id"])
			
			fc_dt = datetime.datetime.utcfromtimestamp(fc_ts + timezone_offset)
			fc_time_str = fc_dt.strftime("%H:%M")
			
			col_center_x = start_x + (i * col_width) + (col_width // 2)
			
			try:
				w_t, _ = draw.textsize(fc_time_str, font=FONT_SANS(22))
			except AttributeError:
				l, t, r, b = draw.textbbox((0, 0), fc_time_str, font=FONT_SANS(22))
				w_t = r - l
			draw.text((col_center_x - w_t//2, 515), fc_time_str, font=FONT_SANS(22), fill=0)
			
			draw_weather_icon(draw, (col_center_x, 595), 85, fc_state)
			
			fc_temp_str = "{0}°C".format(fc_temp)
			try:
				w_temp, _ = draw.textsize(fc_temp_str, font=FONT_SANS(24))
			except AttributeError:
				l, t, r, b = draw.textbbox((0, 0), fc_temp_str, font=FONT_SANS(24))
				w_temp = r - l
			draw.text((col_center_x - w_temp//2, 650), fc_temp_str, font=FONT_SANS(24), fill=0)
			
			if lang == "en":
				fc_desc_display = en_desc_mapping.get(fc_desc_raw.lower(), fc_desc_raw.capitalize())
				fc_desc_font = FONT_SANS(18)
			else:
				fc_desc_display = fc_desc_cn
				fc_desc_font = FONT_CHINESE(18)
				
			try:
				w_desc = draw.textsize(fc_desc_display, font=fc_desc_font)[0]
			except AttributeError:
				l, t, r, b = draw.textbbox((0, 0), fc_desc_display, font=fc_desc_font)
				w_desc = r - l
			draw.text((col_center_x - w_desc//2, 680), fc_desc_display, font=fc_desc_font, fill=0)
			
			if i < 3:
				sep_x = start_x + (i + 1) * col_width
				draw.line([(sep_x, 508), (sep_x, 702)], fill=0, width=1)
				
		# Divider line
		draw.line([(0, 710), (1024, 710)], fill=0, width=1)
		
		# Read language font/labels
		if lang == "en":
			status_font = FONT_SANS(18)
			btn_font = FONT_SANS(14)
			week_str = "Week {0}".format(week_num)
			days_english = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
			day_of_week = days_english[now.weekday()]
			btn_rotate_lbl = "Rotate"
			btn_exit_lbl = "Exit"
		else:
			status_font = FONT_CHINESE(20)
			btn_font = FONT_CHINESE(18)
			week_str = "第{0}周".format(week_num)
			days_chinese = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
			day_of_week = days_chinese[now.weekday()]
			btn_rotate_lbl = "旋转"
			btn_exit_lbl = "退出"

		# STATUS BAR (Y = 710 to 758)
		draw.text((60, 722), week_str, font=status_font, fill=0)
		draw_sunrise_graphic(draw, (230, 735), 24)
		draw.text((250, 722), "{0}".format(sunrise_str), font=FONT_SANS(20), fill=0)
		draw_sunset_graphic(draw, (440, 735), 24)
		draw.text((460, 722), "{0}".format(sunset_str), font=FONT_SANS(20), fill=0)
		draw.text((610, 722), day_of_week, font=status_font, fill=0)
		
		# Visual Buttons (Rotate, Lang, Exit)
		# Button 1: Rotate
		draw.rectangle([740, 716, 810, 752], outline=0, width=2)
		try:
			w_lbl = draw.textsize(btn_rotate_lbl, font=btn_font)[0]
		except AttributeError:
			l, t, r, b = draw.textbbox((0, 0), btn_rotate_lbl, font=btn_font)
			w_lbl = r - l
		draw.text((740 + (70 - w_lbl)//2, 722), btn_rotate_lbl, font=btn_font, fill=0)
		
		# Button 2: Lang
		draw.rectangle([830, 716, 900, 752], outline=0, width=2)
		try:
			w_lbl = draw.textsize("中/EN", font=btn_font)[0]
		except AttributeError:
			l, t, r, b = draw.textbbox((0, 0), "中/EN", font=btn_font)
			w_lbl = r - l
		draw.text((830 + (70 - w_lbl)//2, 722), "中/EN", font=btn_font, fill=0)
		
		# Button 3: Exit
		draw.rectangle([920, 716, 990, 752], outline=0, width=2)
		try:
			w_lbl = draw.textsize(btn_exit_lbl, font=btn_font)[0]
		except AttributeError:
			l, t, r, b = draw.textbbox((0, 0), btn_exit_lbl, font=btn_font)
			w_lbl = r - l
		draw.text((920 + (70 - w_lbl)//2, 722), btn_exit_lbl, font=btn_font, fill=0)
		
		# Draw Author Signature
		signature = " by Gu0 Qiang"
		try:
			w_sig = draw.textsize(signature, font=FONT_SANS(12))[0]
		except AttributeError:
			l, t, r, b = draw.textbbox((0, 0), signature, font=FONT_SANS(12))
			w_sig = r - l
		draw.text(((1024 - w_sig)//2, 742), signature, font=FONT_SANS(12), fill=0)
		
		# Rotate 90 degrees clockwise (Image.ROTATE_270) to display correctly on portrait hardware framebuffer
		image = image.transpose(Image.ROTATE_270)
		
	else:
		# 2b. Setup Image Canvas (758x1024 Grayscale Portrait)
		image = Image.new("L", (758, 1024), 255) # 255 = White
		draw = ImageDraw.Draw(image)
		
		# Weather description layout based on language
		en_desc_mapping = {
			"clear sky": "Clear Sky",
			"few clouds": "Few Clouds",
			"scattered clouds": "Scattered",
			"broken clouds": "Broken",
			"overcast clouds": "Overcast",
			"light rain": "Light Rain",
			"moderate rain": "Mod. Rain",
			"heavy intensity rain": "Heavy Rain",
			"snow": "Snow",
			"light snow": "Light Snow"
		}
		if lang == "en":
			desc_text = en_desc_mapping.get(current_desc.lower(), current_desc.capitalize())
			desc_font = FONT_SANS(44)
		else:
			desc_text = current_desc_cn
			desc_font = FONT_CHINESE(48)
			
		# SECTION 1: TOP SECTION (Y = 0 to 220)
		draw_weather_icon(draw, (110, 110), 140, current_state)
		draw.text((230, 20), desc_text, font=desc_font, fill=0)
		draw.text((230, 140), "{0}°C".format(current_temp), font=FONT_SERIF(36), fill=0)
		
		try:
			w_city = draw.textsize(city_name, font=FONT_CHINESE(48))[0]
		except AttributeError:
			l, t, r, b = draw.textbbox((0, 0), city_name, font=FONT_CHINESE(48))
			w_city = r - l
		draw.text((728 - w_city, 20), city_name, font=FONT_CHINESE(48), fill=0)
		
		draw_string_7seg(draw, 488, 110, date_str, 40, 75, space=10, thickness=8)
		draw.line([(0, 220), (758, 220)], fill=0, width=2)
		
		# SECTION 2: MIDDLE SECTION (Giant Real-time Clock, Y = 220 to 520)
		clock_w = 120 * 4 + 24 + 30 * 4
		clock_x_start = (758 - clock_w) // 2
		draw_string_7seg(draw, clock_x_start, 250, time_str, 120, 220, space=30, thickness=24)
		draw.line([(0, 520), (758, 520)], fill=0, width=2)
		
		# SECTION 3: BOTTOM SECTION (4-column Forecast, Y = 520 to 950)
		col_width = 180
		start_x = (758 - 180 * 4) // 2
		
		for i in range(4):
			fc = data["list"][i + 1]
			fc_ts = fc["dt"]
			fc_temp = int(round(fc["main"]["temp"]))
			fc_desc_raw = fc["weather"][0]["description"]
			fc_desc_cn = desc_mapping.get(fc_desc_raw.lower(), fc_desc_raw.capitalize())
			fc_state = get_weather_state(fc["weather"][0]["id"])
			
			fc_dt = datetime.datetime.utcfromtimestamp(fc_ts + timezone_offset)
			fc_time_str = fc_dt.strftime("%H:%M")
			
			col_center_x = start_x + (i * col_width) + (col_width // 2)
			
			try:
				w_t, _ = draw.textsize(fc_time_str, font=FONT_SANS(24))
			except AttributeError:
				l, t, r, b = draw.textbbox((0, 0), fc_time_str, font=FONT_SANS(24))
				w_t = r - l
			draw.text((col_center_x - w_t//2, 550), fc_time_str, font=FONT_SANS(24), fill=0)
			
			draw_weather_icon(draw, (col_center_x, 700), 110, fc_state)
			
			fc_temp_str = "{0}°C".format(fc_temp)
			try:
				w_temp, _ = draw.textsize(fc_temp_str, font=FONT_SANS(28))
			except AttributeError:
				l, t, r, b = draw.textbbox((0, 0), fc_temp_str, font=FONT_SANS(28))
				w_temp = r - l
			draw.text((col_center_x - w_temp//2, 820), fc_temp_str, font=FONT_SANS(28), fill=0)
			
			if lang == "en":
				fc_desc_display = en_desc_mapping.get(fc_desc_raw.lower(), fc_desc_raw.capitalize())
				fc_desc_font = FONT_SANS(18)
			else:
				fc_desc_display = fc_desc_cn
				fc_desc_font = FONT_CHINESE(22)
				
			try:
				w_desc = draw.textsize(fc_desc_display, font=fc_desc_font)[0]
			except AttributeError:
				l, t, r, b = draw.textbbox((0, 0), fc_desc_display, font=fc_desc_font)
				w_desc = r - l
			draw.text((col_center_x - w_desc//2, 880), fc_desc_display, font=fc_desc_font, fill=0)
			
			if i < 3:
				sep_x = start_x + (i + 1) * col_width
				draw.line([(sep_x, 540), (sep_x, 920)], fill=0, width=1)
				
		draw.line([(0, 950), (758, 950)], fill=0, width=1)
		
		# Read language font/labels
		if lang == "en":
			status_font = FONT_SANS(20)
			btn_font = FONT_SANS(14)
			week_str = "Week {0}".format(week_num)
			days_english = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
			day_of_week = days_english[now.weekday()]
			btn_rotate_lbl = "Rotate"
			btn_exit_lbl = "Exit"
		else:
			status_font = FONT_CHINESE(22)
			btn_font = FONT_CHINESE(18)
			week_str = "第{0}周".format(week_num)
			days_chinese = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
			day_of_week = days_chinese[now.weekday()]
			btn_rotate_lbl = "旋转"
			btn_exit_lbl = "退出"

		# STATUS BAR (Y = 950 to 1024)
		draw.text((20, 966), week_str, font=status_font, fill=0)
		draw.text((110, 966), day_of_week, font=status_font, fill=0)
		draw_sunrise_graphic(draw, (240, 979), 24)
		draw.text((260, 966), "{0}".format(sunrise_str), font=FONT_SANS(22), fill=0)
		draw_sunset_graphic(draw, (360, 979), 24)
		draw.text((380, 966), "{0}".format(sunset_str), font=FONT_SANS(22), fill=0)
		
		# Visual Buttons (Rotate, Lang, Exit)
		# Button 1: Rotate
		draw.rectangle([480, 960, 550, 996], outline=0, width=2)
		try:
			w_lbl = draw.textsize(btn_rotate_lbl, font=btn_font)[0]
		except AttributeError:
			l, t, r, b = draw.textbbox((0, 0), btn_rotate_lbl, font=btn_font)
			w_lbl = r - l
		draw.text((480 + (70 - w_lbl)//2, 966), btn_rotate_lbl, font=btn_font, fill=0)
		
		# Button 2: Lang
		draw.rectangle([570, 960, 640, 996], outline=0, width=2)
		try:
			w_lbl = draw.textsize("中/EN", font=btn_font)[0]
		except AttributeError:
			l, t, r, b = draw.textbbox((0, 0), "中/EN", font=btn_font)
			w_lbl = r - l
		draw.text((570 + (70 - w_lbl)//2, 966), "中/EN", font=btn_font, fill=0)
		
		# Button 3: Exit
		draw.rectangle([660, 960, 730, 996], outline=0, width=2)
		try:
			w_lbl = draw.textsize(btn_exit_lbl, font=btn_font)[0]
		except AttributeError:
			l, t, r, b = draw.textbbox((0, 0), btn_exit_lbl, font=btn_font)
			w_lbl = r - l
		draw.text((660 + (70 - w_lbl)//2, 966), btn_exit_lbl, font=btn_font, fill=0)
		
		# Draw Author Signature
		signature = " by Gu0 Qiang"
		try:
			w_sig = draw.textsize(signature, font=FONT_SANS(12))[0]
		except AttributeError:
			l, t, r, b = draw.textbbox((0, 0), signature, font=FONT_SANS(12))
			w_sig = r - l
		draw.text(((758 - w_sig)//2, 1006), signature, font=FONT_SANS(12), fill=0)
		
	# 3. Output PNG
	image.save(OUTPUT_PATH, "PNG")
	print("Dashboard rendered successfully to {0}".format(OUTPUT_PATH))

if __name__ == "__main__":
	main()
