#!/bin/sh
# ==============================================================================
# KINDLE WEATHER STATION EXECUTION WRAPPER
# ==============================================================================
# WARNING: MUST be saved with Unix (LF) line endings.
# ==============================================================================

# ------------------------------------------------------------------------------
# USER CONFIGURATION
# ------------------------------------------------------------------------------
API_KEY="YOUR_OPENWEATHERMAP_API_KEY"
CITY_NAME="Shanghai,CN"
INTERVAL=600  # Wake up every 10 minutes (600 seconds)

# ------------------------------------------------------------------------------
# PATHS AND PLACES
# ------------------------------------------------------------------------------
EXT_DIR="/mnt/us/extensions/weather-station"
PIDFILE="$EXT_DIR/weather.pid"
STOP_FILE="/mnt/us/stop-weather"
LOG_FILE="$EXT_DIR/weather.log"

PYTHON_SCRIPT="$EXT_DIR/render.py"
OUTPUT_PNG="/tmp/output.png"
[ -f "$OUTPUT_PNG" ] || OUTPUT_PNG="$EXT_DIR/output.png"

# ------------------------------------------------------------------------------
# SYSTEM FUNCTIONS
# ------------------------------------------------------------------------------

# Write logs with timestamp
log() {
	echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE" 2>/dev/null
	echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Clear the e-ink screen to prevent ghosting
clear_screen() {
	/usr/sbin/eips -c >/dev/null 2>&1 \
		|| /usr/bin/eips -c >/dev/null 2>&1 \
		|| eips -c >/dev/null 2>&1
	sleep 1
	/usr/sbin/eips -c >/dev/null 2>&1 \
		|| /usr/bin/eips -c >/dev/null 2>&1 \
		|| eips -c >/dev/null 2>&1
	sleep 1
}

# Display a compiled PNG full screen
display_image() {
	local img="$1"
	/usr/sbin/eips -g "$img" >/dev/null 2>&1 \
		|| /usr/bin/eips -g "$img" >/dev/null 2>&1 \
		|| eips -g "$img" >/dev/null 2>&1
}

# Check for USB host connection or active charging
is_usb_connected() {
	for online_file in /sys/class/power_supply/*/online; do
		if [ -f "$online_file" ] && [ "$(cat "$online_file")" = "1" ]; then
			return 0
		fi
	done
	
	local charging_lipc=$(lipc-get-prop com.lab126.powerd charging 2>/dev/null)
	if [ "$charging_lipc" = "Yes" ] || [ "$charging_lipc" = "1" ]; then
		return 0
	fi
	
	return 1
}

# Turn Wi-Fi on
wifi_on() {
	lipc-set-prop com.lab126.cmd wirelessEnable 1 >/dev/null 2>&1
	lipc-set-prop com.lab126.wifid enable 1 >/dev/null 2>&1
}

# Turn Wi-Fi off
wifi_off() {
	lipc-set-prop com.lab126.cmd wirelessEnable 0 >/dev/null 2>&1
	lipc-set-prop com.lab126.wifid enable 0 >/dev/null 2>&1
}

# Wait for Wi-Fi association
wait_for_wifi() {
	for i in $(seq 1 30); do
		local cm_state=$(lipc-get-prop com.lab126.wifid cmState 2>/dev/null)
		if [ "$cm_state" = "CONNECTED" ] || [ "$cm_state" = "connected" ]; then
			return 0
		fi
		sleep 1
	done
	return 1
}

# Locate the touchscreen input event file
find_touchscreen() {
	local event_id=$(awk '/Handlers/ {handlers=$0} /touchscreen|mxt|zforce|cyttsp/ {print handlers}' /proc/bus/input/devices 2>/dev/null | grep -o 'event[0-9]*' | head -n1)
	if [ ! -z "$event_id" ]; then
		echo "/dev/input/$event_id"
		return 0
	fi
	
	for ev in event0 event1 event2 event3; do
		if [ -c "/dev/input/$ev" ]; then
			echo "/dev/input/$ev"
			return 0
		fi
	done
	return 1
}

# Stop Java GUI framework
stop_framework() {
	lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null
	initctl stop lab126_gui >/dev/null 2>&1
	stop lab126_gui >/dev/null 2>&1
	stop framework >/dev/null 2>&1
}

# Start Java GUI framework
start_framework() {
	lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
	initctl start lab126_gui >/dev/null 2>&1
	start lab126_gui >/dev/null 2>&1
	start framework >/dev/null 2>&1
}

# Set sleep wakeup timer via RTC wake alarm
set_wakeup_alarm() {
	local seconds="$1"
	
	if [ -f /sys/class/rtc/rtc1/wakealarm ]; then
		echo 0 > /sys/class/rtc/wakealarm
	fi
	if [ -f /sys/class/rtc/rtc0/wakealarm ]; then
		echo 0 > /sys/class/wakealarm
	fi
	
	if rtcwake -d /dev/rtc1 -m no -s "$seconds" >/dev/null 2>&1; then
		return 0
	elif rtcwake -d /dev/rtc0 -m no -s "$seconds" >/dev/null 2>&1; then
		return 0
	fi
	
	if [ -f /sys/class/rtc/rtc1/wakealarm ]; then
		echo "+$seconds" > /sys/class/wakealarm 2>/dev/null \
			|| echo "$(( $(date +%s) + seconds ))" > /sys/class/rtc/rtc1/wakealarm
		return 0
	elif [ -f /sys/class/rtc/rtc0/wakealarm ]; then
		echo "+$seconds" > /sys/class/wakealarm 2>/dev/null \
			|| echo "$(( $(date +%s) + seconds ))" > /sys/class/rtc/rtc0/wakealarm
		return 0
	fi
	
	return 1
}

# Suspend system to RAM (sleep state)
suspend_device() {
	echo "mem" > /sys/power/state
}

# System cleanup during script lifecycle termination
cleanup() {
	rm -f "$PIDFILE" "$STOP_FILE" "$EXT_DIR/stop"
	wifi_on
	clear_screen
	/usr/sbin/eips 2 10 "Restoring Kindle GUI..." >/dev/null 2>&1 || eips 2 10 "Restoring Kindle GUI..." >/dev/null 2>&1
	sleep 2
	start_framework
}

# ------------------------------------------------------------------------------
# MAIN EXECUTION ROUTER
# ------------------------------------------------------------------------------
case "$1" in
	start)
		if [ -f "$PIDFILE" ]; then
			PID=$(cat "$PIDFILE")
			if kill -0 "$PID" >/dev/null 2>&1; then
				echo "Weather Station is already running (PID: $PID)."
				exit 0
			fi
			rm -f "$PIDFILE"
		fi
		
		# Clear existing log
		rm -f "$LOG_FILE"

		
		# Spawn independent process session daemon via sh to bypass noexec
		setsid sh "$0" daemon >"$LOG_FILE" 2>&1 &
		sleep 2
		
		if [ -f "$PIDFILE" ]; then
			echo "Weather Station started."
		else
			echo "Failed to start Weather Station."
		fi
		exit 0
		;;
		
	stop)
		touch "$STOP_FILE"
		touch "$EXT_DIR/stop"
		if [ -f "$PIDFILE" ]; then
			PID=$(cat "$PIDFILE")
			if kill -0 "$PID" >/dev/null 2>&1; then
				kill "$PID"
				sleep 2
			fi
		fi
		start_framework
		echo "Weather Station stopped."
		exit 0
		;;
		
	daemon)
		echo "$$" > "$PIDFILE"
		trap "cleanup; exit 0" SIGINT SIGTERM SIGHUP
		
		log "Weather Station daemon started."
		


		
		# Halt native GUI
		log "Stopping framework GUI."
		stop_framework
		clear_screen
		
		while true; do
			# USB exit check
			if is_usb_connected || [ -f "$STOP_FILE" ] || [ -f "$EXT_DIR/stop" ]; then
				log "USB connection or stop flag detected. Cleaning up."
				cleanup
				exit 0
			fi
			
			# Check if weather data fetch is needed (every 10 minutes)
			local fetch_needed=$(/mnt/us/python3/bin/python3.9 -c "import os, time; print(1 if not os.path.exists('/tmp/weather_forecast.json') or time.time() - os.path.getmtime('/tmp/weather_forecast.json') > 600 else 0)")
			
			if [ "$fetch_needed" = "1" ]; then
				log "Weather update needed. Enabling WiFi."
				wifi_on
				if wait_for_wifi; then
					log "WiFi connected. Executing Python Pillow renderer (fetch mode)."
					/mnt/us/python3/bin/python3.9 -u "$PYTHON_SCRIPT" "$API_KEY" "$CITY_NAME"
				else
					log "WiFi timeout. Attempting to render with cache."
					/mnt/us/python3/bin/python3.9 -u "$PYTHON_SCRIPT" "$API_KEY" "$CITY_NAME"
				fi
				log "Disabling WiFi."
				wifi_off
			else
				log "Using cached weather data. Executing renderer."
				/mnt/us/python3/bin/python3.9 -u "$PYTHON_SCRIPT" "$API_KEY" "$CITY_NAME"
			fi
			
			local render_err=$?
			if [ $render_err -eq 0 ]; then
				log "Dashboard rendered successfully. Flushing display."
				if [ -f "/tmp/output.png" ]; then
					display_image "/tmp/output.png"
				elif [ -f "$EXT_DIR/output.png" ]; then
					display_image "$EXT_DIR/output.png"
				fi
			else
				log "Error: Python rendering failed with exit code $render_err."
			fi
			
			# Exit checks before sleeping
			if is_usb_connected || [ -f "$STOP_FILE" ] || [ -f "$EXT_DIR/stop" ]; then
				cleanup
				exit 0
			fi
			
			# Calculate sleep time to the next colon transition (7s on / 3s off)
			local sec=$(date +%S)
			sec=${sec#0}
			[ -z "$sec" ] && sec=0
			local sec_mod=$((sec % 10))
			local next_sleep=3
			if [ $sec_mod -lt 7 ]; then
				next_sleep=$((7 - sec_mod))
			else
				next_sleep=$((10 - sec_mod))
			fi
			
			# Interactive Touch Monitor (using calculated next_sleep as timeout)
			local touch_dev=$(find_touchscreen)
			if [ ! -z "$touch_dev" ]; then
				log "Monitoring touchscreen with monitor_touch.py ($next_sleep s window)..."
				while true; do
					/mnt/us/python3/bin/python3.9 -u "$EXT_DIR/monitor_touch.py" "$touch_dev" "$next_sleep" "$EXT_DIR"
					local touch_res=$?
					if [ $touch_res -eq 20 ]; then
						log "Touch action: EXIT. Shutting down."
						cleanup
						exit 0
					elif [ $touch_res -eq 10 ]; then
						log "Touch action: TOGGLE. Switching orientation."
						local cur_orient="portrait"
						if [ -f "$EXT_DIR/orientation.state" ]; then
							cur_orient=$(cat "$EXT_DIR/orientation.state" | tr -d ' \r\n')
						fi
						if [ "$cur_orient" = "landscape" ]; then
							echo "portrait" > "$EXT_DIR/orientation.state"
						else
							echo "landscape" > "$EXT_DIR/orientation.state"
						fi
						log "New orientation: $(cat "$EXT_DIR/orientation.state"). Redrawing immediately."
						/mnt/us/python3/bin/python3.9 -u "$PYTHON_SCRIPT" "$API_KEY" "$CITY_NAME"
						if [ -f "/tmp/output.png" ]; then
							display_image "/tmp/output.png"
						elif [ -f "$EXT_DIR/output.png" ]; then
							display_image "$EXT_DIR/output.png"
						fi
						# Recalculate sleep time for remaining segment
						sec=$(date +%S)
						sec=${sec#0}
						[ -z "$sec" ] && sec=0
						sec_mod=$((sec % 10))
						if [ $sec_mod -lt 7 ]; then
							next_sleep=$((7 - sec_mod))
						else
							next_sleep=$((10 - sec_mod))
						fi
						continue
					elif [ $touch_res -eq 15 ]; then
						log "Touch action: LANG. Switching language."
						local cur_lang="zh"
						if [ -f "$EXT_DIR/language.state" ]; then
							cur_lang=$(cat "$EXT_DIR/language.state" | tr -d ' \r\n')
						fi
						if [ "$cur_lang" = "en" ]; then
							echo "zh" > "$EXT_DIR/language.state"
						else
							echo "en" > "$EXT_DIR/language.state"
						fi
						log "New language: $(cat "$EXT_DIR/language.state"). Redrawing immediately."
						/mnt/us/python3/bin/python3.9 -u "$PYTHON_SCRIPT" "$API_KEY" "$CITY_NAME"
						if [ -f "/tmp/output.png" ]; then
							display_image "/tmp/output.png"
						elif [ -f "$EXT_DIR/output.png" ]; then
							display_image "$EXT_DIR/output.png"
						fi
						# Recalculate sleep time
						sec=$(date +%S)
						sec=${sec#0}
						[ -z "$sec" ] && sec=0
						sec_mod=$((sec % 10))
						if [ $sec_mod -lt 7 ]; then
							next_sleep=$((7 - sec_mod))
						else
							next_sleep=$((10 - sec_mod))
						fi
						continue
					else
						# Timeout or no action
						break
					fi
				done
			else
				log "No touchscreen found. Sleeping $next_sleep s."
				sleep "$next_sleep"
			fi
			
			# Check again before loop repeats
			if is_usb_connected || [ -f "$STOP_FILE" ] || [ -f "$EXT_DIR/stop" ]; then
				cleanup
				exit 0
			fi
		done
		;;
		
	*)
		echo "Usage: $0 {start|stop|daemon}"
		exit 1
		;;
esac
