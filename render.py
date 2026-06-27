#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# KINDLE WEATHER DASHBOARD - PERSISTENT PROCESS
# ==============================================================================
# Single long-running process that handles rendering, touch input, weather
# fetching, and system management. Eliminates repeated Python startup for
# instant button response (<0.5s vs 3-5s).
#
# Enforces Unix (LF) line endings. Python 2/3 compatible.
# ==============================================================================

import os
import sys
import json
import math
import datetime
import socket
import time
import struct
import select
import signal
import glob

socket.setdefaulttimeout(15)

try:
	import subprocess
except ImportError:
	subprocess = None

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
	OUTPUT_PATH = os.path.join(EXT_DIR, "output.png")

CACHE_PATH = "/tmp/weather_forecast.json"
if not os.path.exists("/tmp"):
	CACHE_PATH = os.path.join(EXT_DIR, "weather_forecast.json")

STOP_FILE = "/mnt/us/stop-weather"
WEATHER_INTERVAL = 600  # 10 minutes between API fetches
CACHE_TTL = 300         # 5 minutes cache validity

# Weather description mappings
DESC_MAP_ZH = {
	"clear sky": "晴",
	"few clouds": "少云",
	"scattered clouds": "多云",
	"broken clouds": "多云",
	"overcast clouds": "阴, 多云",
	"light rain": "小雨",
	"moderate rain": "中雨",
	"heavy intensity rain": "大雨",
	"very heavy rain": "暴雨",
	"extreme rain": "极端降雨",
	"freezing rain": "冻雨",
	"light intensity shower rain": "小阵雨",
	"shower rain": "阵雨",
	"heavy intensity shower rain": "大阵雨",
	"light intensity drizzle": "小毛雨",
	"drizzle": "毛雨",
	"snow": "雪",
	"light snow": "小雪",
	"heavy snow": "大雪",
	"sleet": "雨夹雪",
	"mist": "薄雾",
	"fog": "雾",
	"haze": "霾",
	"thunderstorm": "雷暴",
	"thunderstorm with rain": "雷阵雨",
	"thunderstorm with heavy rain": "强雷阵雨",
}

DESC_MAP_EN = {
	"clear sky": "Clear Sky",
	"few clouds": "Few Clouds",
	"scattered clouds": "Scattered",
	"broken clouds": "Broken",
	"overcast clouds": "Overcast",
	"light rain": "Light Rain",
	"moderate rain": "Mod. Rain",
	"heavy intensity rain": "Heavy Rain",
	"snow": "Snow",
	"light snow": "Light Snow",
	"mist": "Mist",
	"fog": "Fog",
	"haze": "Haze",
	"thunderstorm": "T-Storm",
}

# ------------------------------------------------------------------------------
# FONT LOADER HELPER
# ------------------------------------------------------------------------------
_font_cache = {}

def load_system_font(font_names, size):
	cache_key = (tuple(font_names), size)
	if cache_key in _font_cache:
		return _font_cache[cache_key]

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
					font = ImageFont.truetype(full_path, size)
					_font_cache[cache_key] = font
					return font
				except Exception:
					pass
	font = ImageFont.load_default()
	_font_cache[cache_key] = font
	return font

# Load specific typographic styles
FONT_CHINESE = lambda size: load_system_font(["MYingHeiSMedium.ttf", "MYingHeiSBold.ttf", "STSongMedium.ttf", "code2000.ttf", "STKaiMedium.ttf", "arial.ttf"], size)
FONT_SERIF = lambda size: load_system_font(["Caecilia_LT_65_Medium.ttf", "Baskerville-Regular.ttf", "Palatino-Regular.ttf", "times.ttf"], size)
FONT_SANS = lambda size: load_system_font(["Helvetica_LT_65_Medium.ttf", "Futura-Medium.ttf", "Helvetica.ttf", "arial.ttf"], size)

# ------------------------------------------------------------------------------
# TEXT MEASUREMENT HELPER
# ------------------------------------------------------------------------------
def get_text_width(draw, text, font):
	try:
		return draw.textsize(text, font=font)[0]
	except AttributeError:
		l, t, r, b = draw.textbbox((0, 0), text, font=font)
		return r - l

def draw_centered_text(draw, cx, y, text, font, fill=0):
	w = get_text_width(draw, text, font)
	draw.text((cx - w // 2, y), text, font=font, fill=fill)

# ------------------------------------------------------------------------------
# SYSTEM FUNCTIONS
# ------------------------------------------------------------------------------
def _run_cmd(args):
	"""Run a system command, return stdout string or None on failure."""
	if subprocess is None:
		return None
	try:
		result = subprocess.check_output(args, stderr=subprocess.DEVNULL)
		return result.decode("utf-8", errors="replace").strip()
	except Exception:
		return None

def _call_cmd(args):
	"""Run a system command, ignore output."""
	if subprocess is None:
		return
	try:
		subprocess.call(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
	except Exception:
		pass

def get_battery_level():
	"""Read battery percentage (0-100). Returns -1 if unavailable."""
	# Method 1: lipc (most reliable on Kindle)
	val = _run_cmd(["lipc-get-prop", "com.lab126.powerd", "battLevel"])
	if val is not None:
		try:
			return int(val)
		except ValueError:
			pass

	# Method 2: sysfs
	for path in glob.glob("/sys/class/power_supply/*/capacity"):
		try:
			with open(path, "r") as f:
				return int(f.read().strip())
		except Exception:
			pass

	return -1

def get_light_level():
	"""Read frontlight intensity (0-24). Returns -1 if unavailable."""
	val = _run_cmd(["lipc-get-prop", "com.lab126.powerd", "flIntensity"])
	if val is not None:
		try:
			return int(val)
		except ValueError:
			pass
	return -1

def set_light_level(level):
	"""Set frontlight intensity (0-24)."""
	_call_cmd(["lipc-set-prop", "com.lab126.powerd", "flIntensity", str(level)])

def toggle_light():
	"""Toggle frontlight on/off. Returns new state: True=on, False=off."""
	current = get_light_level()
	if current < 0:
		return False  # Not supported

	state_file = os.path.join(EXT_DIR, "light.state")
	if current > 0:
		# Save current level before turning off
		try:
			with open(state_file, "w") as f:
				f.write(str(current))
		except Exception:
			pass
		set_light_level(0)
		return False
	else:
		# Restore saved level or default to 10
		saved = 10
		if os.path.exists(state_file):
			try:
				with open(state_file, "r") as f:
					val = f.read().strip()
				if val.isdigit() and int(val) > 0:
					saved = int(val)
			except Exception:
				pass
		set_light_level(saved)
		return True

def wifi_on():
	_call_cmd(["lipc-set-prop", "com.lab126.cmd", "wirelessEnable", "1"])
	_call_cmd(["lipc-set-prop", "com.lab126.wifid", "enable", "1"])

def wifi_off():
	_call_cmd(["lipc-set-prop", "com.lab126.cmd", "wirelessEnable", "0"])
	_call_cmd(["lipc-set-prop", "com.lab126.wifid", "enable", "0"])

def wait_for_wifi(timeout=30):
	for _ in range(timeout):
		state = _run_cmd(["lipc-get-prop", "com.lab126.wifid", "cmState"])
		if state and state.lower() in ("connected",):
			return True
		time.sleep(1)
	return False

def is_usb_connected():
	"""Check if USB cable is connected or device is charging."""
	for online_file in glob.glob("/sys/class/power_supply/*/online"):
		try:
			with open(online_file, "r") as f:
				if f.read().strip() == "1":
					return True
		except Exception:
			pass
	val = _run_cmd(["lipc-get-prop", "com.lab126.powerd", "charging"])
	if val and val in ("Yes", "1"):
		return True
	return False

def check_stop_files():
	"""Check if stop signal files exist."""
	return os.path.exists(STOP_FILE) or os.path.exists(os.path.join(EXT_DIR, "stop"))

def display_image(path):
	"""Display a PNG on the e-ink screen via eips."""
	for cmd in ["/usr/sbin/eips", "/usr/bin/eips", "eips"]:
		try:
			subprocess.call([cmd, "-g", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
			return
		except Exception:
			pass

def clear_screen():
	"""Clear the e-ink display."""
	for cmd in ["/usr/sbin/eips", "/usr/bin/eips", "eips"]:
		try:
			subprocess.call([cmd, "-c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
			return
		except Exception:
			pass

def find_touchscreen():
	"""Find the touchscreen input device path."""
	try:
		with open("/proc/bus/input/devices", "r") as f:
			content = f.read()
		# Look for touchscreen handlers
		import re
		blocks = content.split("\n\n")
		for block in blocks:
			if any(kw in block.lower() for kw in ["touchscreen", "mxt", "zforce", "cyttsp"]):
				match = re.search(r"event(\d+)", block)
				if match:
					dev = "/dev/input/event" + match.group(1)
					if os.path.exists(dev):
						return dev
	except Exception:
		pass

	# Fallback: try common event devices
	for ev in ["event0", "event1", "event2", "event3"]:
		dev = "/dev/input/" + ev
		if os.path.exists(dev):
			return dev
	return None

# ------------------------------------------------------------------------------
# STATE FILE HELPERS
# ------------------------------------------------------------------------------
def read_state(name, default=""):
	"""Read a .state file from EXT_DIR."""
	path = os.path.join(EXT_DIR, name + ".state")
	if os.path.exists(path):
		try:
			with open(path, "r") as f:
				return f.read().strip().lower()
		except Exception:
			pass
	return default

def write_state(name, value):
	"""Write a .state file to EXT_DIR."""
	path = os.path.join(EXT_DIR, name + ".state")
	try:
		with open(path, "w") as f:
			f.write(value + "\n")
	except Exception:
		pass

# ------------------------------------------------------------------------------
# SEVEN-SEGMENT LCD DISPLAY DRAWING LOGIC
# ------------------------------------------------------------------------------
def draw_digit_7seg(draw, x, y, w, h, char, thickness=12):
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

def draw_string_7seg(draw, x, y, string, char_w, char_h, space=15, thickness=12, show_colon=True):
	curr_x = x
	for char in string:
		if char == ':':
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
# WEATHER ICON DRAWING
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
	bx = x + r//3
	by = y - r//4
	br = int(r * 0.7)
	draw.ellipse([bx - br//2, by - br//4, bx - br//6, by + br//4], fill=255, outline=0, width=4)
	draw.ellipse([bx - br//3, by - br//2, bx + br//3, by + br//6], fill=255, outline=0, width=4)
	draw.ellipse([bx + br//6, by - br//4, bx + br//2, by + br//4], fill=255, outline=0, width=4)
	draw.rectangle([bx - br//2 + 2, by, bx + br//2 - 2, by + br//4], fill=255)
	draw.line([bx - br//2, by + br//4, bx + br//2, by + br//4], fill=0, width=4)
	draw.ellipse([x - r//2, y - r//4, x - r//6, y + r//4], fill=255, outline=0, width=4)
	draw.ellipse([x - r//3, y - r//2, x + r//3, y + r//6], fill=255, outline=0, width=4)
	draw.ellipse([x + r//6, y - r//4, x + r//2, y + r//4], fill=255, outline=0, width=4)
	draw.rectangle([x - r//2 + 2, y, x + r//2 - 2, y + r//4], fill=255)
	draw.line([x - r//2, y + r//4, x + r//2, y + r//4], fill=0, width=4)

def draw_sunny_cloudy_icon(draw, center, size):
	x, y = center
	r = size // 2
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

# ------------------------------------------------------------------------------
# SUNRISE / SUNSET GRAPHICS
# ------------------------------------------------------------------------------
def draw_sunrise_graphic(draw, center, size):
	x, y = center
	r = size // 2
	draw.line([x - r, y + 4, x + r, y + 4], fill=0, width=2)
	draw.arc([x - r//2, y - r//2 + 4, x + r//2, y + r//2 + 4], start=180, end=360, fill=0, width=2)
	draw.line([x, y - r//2, x, y - r], fill=0, width=2)
	draw.line([x - r//3, y - r//3, x - r//2 - 2, y - r//2 - 2], fill=0, width=2)
	draw.line([x + r//3, y - r//3, x + r//2 + 2, y - r//2 - 2], fill=0, width=2)

def draw_sunset_graphic(draw, center, size):
	x, y = center
	r = size // 2
	draw.line([x - r, y + 4, x + r, y + 4], fill=0, width=2)
	draw.arc([x - r//2, y - r//3 + 4, x + r//2, y + 2*r//3 + 4], start=180, end=360, fill=0, width=2)
	draw.line([x, y - r//4, x, y - r//2], fill=0, width=2)
	draw.line([x - r//3, y - r//6, x - r//2, y - r//3], fill=0, width=2)
	draw.line([x + r//3, y - r//6, x + r//2, y - r//3], fill=0, width=2)

# ------------------------------------------------------------------------------
# BATTERY ICON DRAWING
# ------------------------------------------------------------------------------
def draw_battery_icon(draw, x, y, level, size=18):
	"""Draw a battery icon with fill level at position (x, y)."""
	bw = int(size * 2)    # battery body width
	bh = size             # battery body height
	nub_w = 3             # positive terminal nub width
	nub_h = bh // 3       # positive terminal nub height

	# Battery body outline
	draw.rectangle([x, y, x + bw, y + bh], outline=0, width=2)
	# Positive terminal nub
	draw.rectangle([x + bw, y + (bh - nub_h) // 2, x + bw + nub_w, y + (bh + nub_h) // 2], fill=0)

	# Fill level (inside the body)
	if level > 0:
		fill_w = int((bw - 6) * min(level, 100) / 100)
		if fill_w > 0:
			draw.rectangle([x + 3, y + 3, x + 3 + fill_w, y + bh - 3], fill=0)

# ------------------------------------------------------------------------------
# BUTTON DRAWING HELPER
# ------------------------------------------------------------------------------
def draw_button(draw, x1, y1, x2, y2, label, font):
	"""Draw a button rectangle with centered label."""
	draw.rectangle([x1, y1, x2, y2], outline=0, width=2)
	w = get_text_width(draw, label, font)
	btn_w = x2 - x1
	draw.text((x1 + (btn_w - w) // 2, y1 + 3), label, font=font, fill=0)

# ------------------------------------------------------------------------------
# API FETCHING
# ------------------------------------------------------------------------------
def fetch_forecast(api_key, city):
	encoded_city = urllib_parse.quote(city)
	url = "https://api.openweathermap.org/data/2.5/forecast?q={0}&units=metric&appid={1}".format(encoded_city, api_key)

	import ssl
	try:
		context = ssl._create_unverified_context()
		response = urllib2.urlopen(url, timeout=15, context=context)
	except AttributeError:
		response = urllib2.urlopen(url, timeout=15)

	return json.loads(response.read().decode('utf-8'))

def load_or_fetch_weather(api_key, city):
	"""Load weather from cache or fetch from API. Manages WiFi automatically."""
	data = None

	# Try cache first
	if os.path.exists(CACHE_PATH):
		mtime = os.path.getmtime(CACHE_PATH)
		if time.time() - mtime < CACHE_TTL:
			try:
				with open(CACHE_PATH, "r", encoding="utf-8") as f:
					data = json.load(f)
				print("Using cached weather forecast data.")
				return data, False  # data, wifi_was_used
			except Exception:
				pass

	# Need fresh data - enable WiFi
	print("Weather update needed. Enabling WiFi.")
	wifi_on()
	wifi_connected = wait_for_wifi()

	if wifi_connected:
		try:
			data = fetch_forecast(api_key, city)
			with open(CACHE_PATH, "w", encoding="utf-8") as f:
				json.dump(data, f)
			print("Weather data fetched and cached.")
			wifi_off()
			return data, True
		except Exception as e:
			print("API fetch failed: {0}".format(e))
	else:
		print("WiFi connection timeout.")

	wifi_off()

	# Fallback to expired cache
	if data is None and os.path.exists(CACHE_PATH):
		try:
			with open(CACHE_PATH, "r", encoding="utf-8") as f:
				data = json.load(f)
			print("Using expired cache data as fallback.")
		except Exception:
			pass

	return data, False

# ------------------------------------------------------------------------------
# TOUCH EVENT MONITORING (merged from monitor_touch.py)
# ------------------------------------------------------------------------------
def monitor_touch(dev_path, timeout_sec, orientation):
	"""
	Monitor touchscreen for events within timeout.
	Returns: "TOGGLE", "LIGHT", "LANG", "EXIT", or "NONE" (timeout)
	"""
	try:
		f = open(dev_path, "rb")
	except Exception:
		time.sleep(timeout_sec)
		return "NONE"

	event_format = "2iHHi"
	event_size = struct.calcsize(event_format)

	x = None
	y = None
	touch_x = None
	touch_y = None

	start_time = time.time()

	while True:
		elapsed = time.time() - start_time
		if elapsed >= timeout_sec:
			break

		r, _, _ = select.select([f], [], [], timeout_sec - elapsed)
		if not r:
			break

		data = f.read(event_size)
		if len(data) < event_size:
			break

		_, _, ev_type, ev_code, ev_val = struct.unpack(event_format, data)

		if ev_type == 3:  # EV_ABS
			if ev_code in [0, 53]:  # ABS_X or ABS_MT_POSITION_X
				x = ev_val
			elif ev_code in [1, 54]:  # ABS_Y or ABS_MT_POSITION_Y
				y = ev_val
		elif ev_type == 1 and ev_code == 330:  # BTN_TOUCH release
			if ev_val == 0 and x is not None and y is not None:
				touch_x = x
				touch_y = y
				break
		elif ev_type == 0 and ev_code == 0:  # EV_SYN
			if x is not None and y is not None:
				touch_x = x
				touch_y = y

	f.close()

	if touch_x is None or touch_y is None:
		touch_x = x
		touch_y = y

	if touch_x is None or touch_y is None:
		return "NONE"

	# Scale coordinates to portrait space (758x1024)
	if touch_x > 2000 or touch_y > 2000:
		touch_x = int(touch_x * 758 / 4096)
		touch_y = int(touch_y * 1024 / 4096)
	elif touch_x > 1024 or touch_y > 1024:
		touch_x = int(touch_x * 758 / 1024)
		touch_y = int(touch_y * 1024 / 1280)

	print("Touch: Raw scaled portrait=({0},{1}) orientation={2}".format(touch_x, touch_y, orientation))

	# Detect button zones
	if orientation == "landscape":
		# After ROTATE_270: landscape point (lx, ly) -> portrait (757-ly, lx)
		# Buttons are at bottom of landscape (ly > 710), so portrait touch_x < ~50
		# Button X ranges map to portrait touch_y
		if touch_x < 120:
			if 675 <= touch_y < 750:
				return "TOGGLE"
			elif 750 <= touch_y < 825:
				return "LIGHT"
			elif 825 <= touch_y < 900:
				return "LANG"
			elif touch_y >= 900:
				return "EXIT"
	else:
		# Portrait: buttons at bottom (y > 950)
		if touch_y > 950:
			if 458 <= touch_x < 535:
				return "TOGGLE"
			elif 535 <= touch_x < 612:
				return "LIGHT"
			elif 612 <= touch_x < 690:
				return "LANG"
			elif touch_x >= 690:
				return "EXIT"

	return "NONE"

# ------------------------------------------------------------------------------
# DASHBOARD RENDERING
# ------------------------------------------------------------------------------
def render_dashboard(data, orientation, lang, battery_level, light_on, show_colon=True):
	"""Render the complete weather dashboard and save to OUTPUT_PATH."""
	# Extract weather data
	timezone_offset = data["city"]["timezone"]
	city_name = data["city"]["name"]
	sunrise_ts = data["city"]["sunrise"]
	sunset_ts = data["city"]["sunset"]

	current_entry = data["list"][0]
	current_temp = int(round(current_entry["main"]["temp"]))
	current_desc = current_entry["weather"][0]["description"]
	current_state = get_weather_state(current_entry["weather"][0]["id"])

	sunrise_dt = datetime.datetime.utcfromtimestamp(sunrise_ts + timezone_offset)
	sunset_dt = datetime.datetime.utcfromtimestamp(sunset_ts + timezone_offset)
	sunrise_str = sunrise_dt.strftime("%H:%M")
	sunset_str = sunset_dt.strftime("%H:%M")

	now = datetime.datetime.now()
	date_str = now.strftime("%m-%d")
	time_str = now.strftime("%H:%M")
	week_num = now.isocalendar()[1]

	# Localized strings
	if lang == "en":
		desc_text = DESC_MAP_EN.get(current_desc.lower(), current_desc.capitalize())
		days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
		day_of_week = days[now.weekday()]
		week_str = "Week {0}".format(week_num)
		btn_rotate_lbl = "Rotate"
		btn_light_lbl = "Light" if not light_on else "Dark"
		btn_lang_lbl = "中/EN"
		btn_exit_lbl = "Exit"
	else:
		desc_text = DESC_MAP_ZH.get(current_desc.lower(), current_desc.capitalize())
		days = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
		day_of_week = days[now.weekday()]
		week_str = "第{0}周".format(week_num)
		btn_rotate_lbl = "旋转"
		btn_light_lbl = "灯:关" if not light_on else "灯:开"
		btn_lang_lbl = "中/EN"
		btn_exit_lbl = "退出"

	if orientation == "landscape":
		image = _render_landscape(
			draw_params=None, data=data, desc_text=desc_text, current_temp=current_temp,
			current_state=current_state, city_name=city_name, date_str=date_str,
			time_str=time_str, show_colon=show_colon, sunrise_str=sunrise_str,
			sunset_str=sunset_str, week_str=week_str, day_of_week=day_of_week,
			battery_level=battery_level, light_on=light_on, lang=lang,
			timezone_offset=timezone_offset,
			btn_rotate_lbl=btn_rotate_lbl, btn_light_lbl=btn_light_lbl,
			btn_lang_lbl=btn_lang_lbl, btn_exit_lbl=btn_exit_lbl,
		)
	else:
		image = _render_portrait(
			draw_params=None, data=data, desc_text=desc_text, current_temp=current_temp,
			current_state=current_state, city_name=city_name, date_str=date_str,
			time_str=time_str, show_colon=show_colon, sunrise_str=sunrise_str,
			sunset_str=sunset_str, week_str=week_str, day_of_week=day_of_week,
			battery_level=battery_level, light_on=light_on, lang=lang,
			timezone_offset=timezone_offset,
			btn_rotate_lbl=btn_rotate_lbl, btn_light_lbl=btn_light_lbl,
			btn_lang_lbl=btn_lang_lbl, btn_exit_lbl=btn_exit_lbl,
		)

	image.save(OUTPUT_PATH, "PNG")

def _render_portrait(data, desc_text, current_temp, current_state, city_name,
                     date_str, time_str, show_colon, sunrise_str, sunset_str,
                     week_str, day_of_week, battery_level, light_on, lang,
                     timezone_offset, btn_rotate_lbl, btn_light_lbl,
                     btn_lang_lbl, btn_exit_lbl, draw_params=None):
	"""Render portrait layout (758x1024)."""
	image = Image.new("L", (758, 1024), 255)
	draw = ImageDraw.Draw(image)

	if lang == "en":
		desc_font = FONT_SANS(44)
		status_font = FONT_SANS(18)
		btn_font = FONT_SANS(14)
	else:
		desc_font = FONT_CHINESE(48)
		status_font = FONT_CHINESE(20)
		btn_font = FONT_CHINESE(16)

	# === SECTION 1: TOP SECTION (Y = 0 to 220) ===
	draw_weather_icon(draw, (110, 110), 140, current_state)
	draw.text((230, 20), desc_text, font=desc_font, fill=0)
	draw.text((230, 140), "{0}\u00b0C".format(current_temp), font=FONT_SERIF(36), fill=0)

	w_city = get_text_width(draw, city_name, FONT_CHINESE(48))
	draw.text((728 - w_city, 20), city_name, font=FONT_CHINESE(48), fill=0)

	draw_string_7seg(draw, 488, 110, date_str, 40, 75, space=10, thickness=8)
	draw.line([(0, 220), (758, 220)], fill=0, width=2)

	# === SECTION 2: MIDDLE SECTION (Giant Clock, Y = 220 to 520) ===
	clock_w = 120 * 4 + 24 + 30 * 4
	clock_x_start = (758 - clock_w) // 2
	draw_string_7seg(draw, clock_x_start, 250, time_str, 120, 220, space=30, thickness=24, show_colon=show_colon)
	draw.line([(0, 520), (758, 520)], fill=0, width=2)

	# === SECTION 3: BOTTOM SECTION (4-column Forecast, Y = 520 to 950) ===
	col_width = 180
	start_x = (758 - 180 * 4) // 2

	for i in range(4):
		fc = data["list"][i + 1]
		fc_ts = fc["dt"]
		fc_temp = int(round(fc["main"]["temp"]))
		fc_desc_raw = fc["weather"][0]["description"]
		fc_state = get_weather_state(fc["weather"][0]["id"])

		fc_dt = datetime.datetime.utcfromtimestamp(fc_ts + timezone_offset)
		fc_time_str = fc_dt.strftime("%H:%M")

		col_center_x = start_x + (i * col_width) + (col_width // 2)

		draw_centered_text(draw, col_center_x, 550, fc_time_str, FONT_SANS(24))
		draw_weather_icon(draw, (col_center_x, 700), 110, fc_state)

		fc_temp_str = "{0}\u00b0C".format(fc_temp)
		draw_centered_text(draw, col_center_x, 820, fc_temp_str, FONT_SANS(28))

		if lang == "en":
			fc_desc_display = DESC_MAP_EN.get(fc_desc_raw.lower(), fc_desc_raw.capitalize())
			fc_desc_font = FONT_SANS(18)
		else:
			fc_desc_display = DESC_MAP_ZH.get(fc_desc_raw.lower(), fc_desc_raw.capitalize())
			fc_desc_font = FONT_CHINESE(22)

		draw_centered_text(draw, col_center_x, 880, fc_desc_display, fc_desc_font)

		if i < 3:
			sep_x = start_x + (i + 1) * col_width
			draw.line([(sep_x, 540), (sep_x, 920)], fill=0, width=1)

	draw.line([(0, 950), (758, 950)], fill=0, width=1)

	# === STATUS BAR (Y = 950 to 1024) ===
	# Left side: info text
	info_y = 964
	draw.text((15, info_y), week_str, font=status_font, fill=0)
	draw.text((100, info_y), day_of_week, font=status_font, fill=0)
	draw_sunrise_graphic(draw, (215, info_y + 13), 24)
	draw.text((233, info_y), sunrise_str, font=FONT_SANS(18), fill=0)
	draw_sunset_graphic(draw, (310, info_y + 13), 24)
	draw.text((328, info_y), sunset_str, font=FONT_SANS(18), fill=0)

	# Battery icon + percentage
	batt_x = 395
	if battery_level >= 0:
		draw_battery_icon(draw, batt_x, info_y + 2, battery_level, size=16)
		draw.text((batt_x + 38, info_y), "{0}%".format(battery_level), font=FONT_SANS(16), fill=0)

	# Right side: 4 buttons
	btn_y1 = 957
	btn_y2 = 993
	btn_w = 63
	btn_gap = 8
	btn_start = 468

	draw_button(draw, btn_start, btn_y1, btn_start + btn_w, btn_y2, btn_rotate_lbl, btn_font)
	draw_button(draw, btn_start + btn_w + btn_gap, btn_y1, btn_start + 2*btn_w + btn_gap, btn_y2, btn_light_lbl, btn_font)
	draw_button(draw, btn_start + 2*(btn_w + btn_gap), btn_y1, btn_start + 3*btn_w + 2*btn_gap, btn_y2, btn_lang_lbl, btn_font)
	draw_button(draw, btn_start + 3*(btn_w + btn_gap), btn_y1, btn_start + 4*btn_w + 3*btn_gap, btn_y2, btn_exit_lbl, btn_font)

	# Author Signature
	signature = " by Gu0 Qiang"
	draw_centered_text(draw, 758 // 2, 1006, signature, FONT_SANS(12))

	return image

def _render_landscape(data, desc_text, current_temp, current_state, city_name,
                      date_str, time_str, show_colon, sunrise_str, sunset_str,
                      week_str, day_of_week, battery_level, light_on, lang,
                      timezone_offset, btn_rotate_lbl, btn_light_lbl,
                      btn_lang_lbl, btn_exit_lbl, draw_params=None):
	"""Render landscape layout (1024x758), then rotate for framebuffer."""
	image = Image.new("L", (1024, 758), 255)
	draw = ImageDraw.Draw(image)

	if lang == "en":
		desc_font = FONT_SANS(44)
		status_font = FONT_SANS(18)
		btn_font = FONT_SANS(14)
	else:
		desc_font = FONT_CHINESE(48)
		status_font = FONT_CHINESE(20)
		btn_font = FONT_CHINESE(16)

	# === SECTION 1: TOP SECTION (Y = 0 to 220) ===
	draw_weather_icon(draw, (120, 110), 140, current_state)
	draw.text((250, 20), desc_text, font=desc_font, fill=0)
	draw.text((250, 140), "{0}\u00b0C".format(current_temp), font=FONT_SERIF(36), fill=0)

	w_city = get_text_width(draw, city_name, FONT_CHINESE(48))
	draw.text((940 - w_city, 20), city_name, font=FONT_CHINESE(48), fill=0)

	draw_string_7seg(draw, 680, 95, date_str, 40, 75, space=10, thickness=8)
	draw.line([(0, 220), (1024, 220)], fill=0, width=2)

	# === SECTION 2: MIDDLE SECTION (Giant Clock, Y = 220 to 500) ===
	clock_w = 120 * 4 + 24 + 30 * 4
	clock_x_start = (1024 - clock_w) // 2
	draw_string_7seg(draw, clock_x_start, 250, time_str, 120, 220, space=30, thickness=24, show_colon=show_colon)
	draw.line([(0, 500), (1024, 500)], fill=0, width=2)

	# === SECTION 3: BOTTOM SECTION (4-column Forecast, Y = 500 to 710) ===
	col_width = 231
	start_x = 50

	for i in range(4):
		fc = data["list"][i + 1]
		fc_ts = fc["dt"]
		fc_temp = int(round(fc["main"]["temp"]))
		fc_desc_raw = fc["weather"][0]["description"]
		fc_state = get_weather_state(fc["weather"][0]["id"])

		fc_dt = datetime.datetime.utcfromtimestamp(fc_ts + timezone_offset)
		fc_time_str = fc_dt.strftime("%H:%M")

		col_center_x = start_x + (i * col_width) + (col_width // 2)

		draw_centered_text(draw, col_center_x, 515, fc_time_str, FONT_SANS(22))
		draw_weather_icon(draw, (col_center_x, 595), 85, fc_state)

		fc_temp_str = "{0}\u00b0C".format(fc_temp)
		draw_centered_text(draw, col_center_x, 650, fc_temp_str, FONT_SANS(24))

		if lang == "en":
			fc_desc_display = DESC_MAP_EN.get(fc_desc_raw.lower(), fc_desc_raw.capitalize())
			fc_desc_font = FONT_SANS(18)
		else:
			fc_desc_display = DESC_MAP_ZH.get(fc_desc_raw.lower(), fc_desc_raw.capitalize())
			fc_desc_font = FONT_CHINESE(18)

		draw_centered_text(draw, col_center_x, 680, fc_desc_display, fc_desc_font)

		if i < 3:
			sep_x = start_x + (i + 1) * col_width
			draw.line([(sep_x, 508), (sep_x, 702)], fill=0, width=1)

	draw.line([(0, 710), (1024, 710)], fill=0, width=1)

	# === STATUS BAR (Y = 710 to 758) ===
	info_y = 722
	draw.text((30, info_y), week_str, font=status_font, fill=0)
	draw_sunrise_graphic(draw, (150, info_y + 13), 24)
	draw.text((168, info_y), sunrise_str, font=FONT_SANS(18), fill=0)
	draw_sunset_graphic(draw, (280, info_y + 13), 24)
	draw.text((298, info_y), sunset_str, font=FONT_SANS(18), fill=0)
	draw.text((380, info_y), day_of_week, font=status_font, fill=0)

	# Battery icon + percentage
	batt_x = 510
	if battery_level >= 0:
		draw_battery_icon(draw, batt_x, info_y + 2, battery_level, size=16)
		draw.text((batt_x + 38, info_y), "{0}%".format(battery_level), font=FONT_SANS(16), fill=0)

	# 4 buttons (right side)
	btn_y1 = 716
	btn_y2 = 752
	btn_w = 65
	btn_gap = 8
	btn_start = 680

	draw_button(draw, btn_start, btn_y1, btn_start + btn_w, btn_y2, btn_rotate_lbl, btn_font)
	draw_button(draw, btn_start + btn_w + btn_gap, btn_y1, btn_start + 2*btn_w + btn_gap, btn_y2, btn_light_lbl, btn_font)
	draw_button(draw, btn_start + 2*(btn_w + btn_gap), btn_y1, btn_start + 3*btn_w + 2*btn_gap, btn_y2, btn_lang_lbl, btn_font)
	draw_button(draw, btn_start + 3*(btn_w + btn_gap), btn_y1, btn_start + 4*btn_w + 3*btn_gap, btn_y2, btn_exit_lbl, btn_font)

	# Author Signature
	signature = " by Gu0 Qiang"
	draw_centered_text(draw, 1024 // 2, 742, signature, FONT_SANS(12))

	# Rotate 90° clockwise for portrait framebuffer
	image = image.transpose(Image.ROTATE_270)

	return image

# ------------------------------------------------------------------------------
# MAIN LOOP (Persistent Process)
# ------------------------------------------------------------------------------
def main():
	if len(sys.argv) < 3:
		print("Usage: render.py <API_KEY> <CITY_NAME>")
		sys.exit(1)

	api_key = sys.argv[1]
	city_query = sys.argv[2]

	# Signal handler for clean shutdown
	running = [True]
	def handle_signal(sig, frame):
		print("Signal {0} received. Shutting down.".format(sig))
		running[0] = False
	signal.signal(signal.SIGINT, handle_signal)
	signal.signal(signal.SIGTERM, handle_signal)

	# Find touchscreen device
	touch_dev = find_touchscreen()
	if touch_dev:
		print("Touchscreen found: {0}".format(touch_dev))
	else:
		print("No touchscreen found. Touch features disabled.")

	# Initial weather data load
	data, _ = load_or_fetch_weather(api_key, city_query)
	if data is None:
		print("FATAL: No weather data available.")
		sys.exit(1)

	last_fetch_time = time.time()

	# Read initial states
	orientation = read_state("orientation", "portrait")
	lang = read_state("language", "zh")

	print("Dashboard persistent process started. Orientation={0}, Lang={1}".format(orientation, lang))

	while running[0]:
		# --- Exit condition checks ---
		if is_usb_connected() or check_stop_files():
			print("USB connection or stop flag detected. Exiting.")
			break

		# --- Weather refresh check (every 10 minutes) ---
		if time.time() - last_fetch_time > WEATHER_INTERVAL:
			print("Refreshing weather data...")
			new_data, _ = load_or_fetch_weather(api_key, city_query)
			if new_data is not None:
				data = new_data
			last_fetch_time = time.time()

		# --- Read system state ---
		battery_level = get_battery_level()
		light_level = get_light_level()
		light_on = light_level > 0

		# --- Calculate colon blink state ---
		sec = datetime.datetime.now().second
		sec_mod = sec % 10
		show_colon = sec_mod < 7

		# --- Render & Display ---
		render_dashboard(data, orientation, lang, battery_level, light_on, show_colon)
		display_image(OUTPUT_PATH)

		# --- Calculate timeout until next colon state change ---
		sec = datetime.datetime.now().second
		sec_mod = sec % 10
		if sec_mod < 7:
			next_timeout = 7 - sec_mod
		else:
			next_timeout = 10 - sec_mod
		if next_timeout <= 0:
			next_timeout = 1

		# --- Monitor touch events ---
		if touch_dev:
			action = monitor_touch(touch_dev, next_timeout, orientation)

			if action == "TOGGLE":
				print("Action: Toggling orientation.")
				orientation = "landscape" if orientation == "portrait" else "portrait"
				write_state("orientation", orientation)
				# Immediate re-render will happen at top of loop

			elif action == "LIGHT":
				print("Action: Toggling frontlight.")
				toggle_light()
				# Light change is instant, no re-render needed for just the light
				# But we re-render to update button label
				continue

			elif action == "LANG":
				print("Action: Switching language.")
				lang = "en" if lang == "zh" else "zh"
				write_state("language", lang)

			elif action == "EXIT":
				print("Action: User requested exit.")
				break

			# "NONE" = timeout, just loop and re-render (colon blink update)
		else:
			time.sleep(next_timeout)

	print("Dashboard persistent process exiting.")
	sys.exit(0)

if __name__ == "__main__":
	main()
