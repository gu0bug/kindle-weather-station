#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# KINDLE TOUCHSCREEN INPUT EVENT MONITOR
# ==============================================================================
# Decodes binary touch events, scales coordinates, and detects button zones.
# Exit code 10 = TOGGLE, Exit code 20 = EXIT, Exit code 0 = TIMEOUT/NONE.
# ==============================================================================

import sys
import os
import struct
import select
import time

def main():
    if len(sys.argv) < 3:
        print("Usage: monitor_touch.py <device_path> <timeout_sec> [ext_dir]")
        sys.exit(0)
        
    dev_path = sys.argv[1]
    timeout = float(sys.argv[2])
    
    ext_dir = "/mnt/us/extensions/weather-station"
    if len(sys.argv) >= 4:
        ext_dir = sys.argv[3]
        
    # Read current orientation state
    orientation = "portrait"
    state_file = os.path.join(ext_dir, "orientation.state")
    if os.path.exists(state_file):
        try:
            with open(state_file, "r") as f:
                orientation = f.read().strip().lower()
        except Exception:
            pass

    try:
        f = open(dev_path, "rb")
    except Exception as e:
        print("Error opening touchscreen device: {0}".format(e))
        sys.exit(0)
        
    # Event format: 2iHHi
    # struct timeval (8 bytes) + type (2 bytes) + code (2 bytes) + value (4 bytes) = 16 bytes
    event_format = "2iHHi"
    event_size = struct.calcsize(event_format)
    
    x = None
    y = None
    touch_x = None
    touch_y = None
    
    start_time = time.time()
    
    while True:
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            break
            
        r, w, x_err = select.select([f], [], [], timeout - elapsed)
        if not r:
            break # Timeout
            
        data = f.read(event_size)
        if len(data) < event_size:
            break
            
        _, _, ev_type, ev_code, ev_val = struct.unpack(event_format, data)
        
        # EV_ABS (type = 3)
        if ev_type == 3:
            if ev_code in [0, 53]: # ABS_X or ABS_MT_POSITION_X
                x = ev_val
            elif ev_code in [1, 54]: # ABS_Y or ABS_MT_POSITION_Y
                y = ev_val
        # EV_KEY (type = 1) and BTN_TOUCH (code = 330)
        elif ev_type == 1 and ev_code == 330:
            if ev_val == 0: # Release
                if x is not None and y is not None:
                    touch_x = x
                    touch_y = y
                    break
        # EV_SYN (type = 0) as fallback
        elif ev_type == 0 and ev_code == 0:
            if x is not None and y is not None:
                touch_x = x
                touch_y = y
                
    # Fallback to last coordinates seen if release event was missed
    if touch_x is None or touch_y is None:
        touch_x = x
        touch_y = y
        
    if touch_x is None or touch_y is None:
        print("No touch event detected (Timeout).")
        sys.exit(0)
        
    orig_x = touch_x
    orig_y = touch_y
    
    # Scale coordinates if they are in 0-4095 range (common for Kindle digitizers)
    # The default coordinate space is mapped to portrait (758x1024)
    if touch_x > 2000 or touch_y > 2000:
        touch_x = int(touch_x * 758 / 4096)
        touch_y = int(touch_y * 1024 / 4096)
    elif touch_x > 1024 or touch_y > 1024:
        # Some digitizers report 0-1024 / 0-1280, scale to 758x1024
        touch_x = int(touch_x * 758 / 1024)
        touch_y = int(touch_y * 1024 / 1280)
        
    print("Detected touch: Raw=({0},{1}) Scaled_Portrait=({2},{3}) Orientation={4}".format(orig_x, orig_y, touch_x, touch_y, orientation))
    
    # Check zones
    if orientation == "landscape":
        # Landscape maps visually to horizontal layout rotated 90 deg clockwise.
        # Bottom of landscape (Y > 710) maps to LEFT of portrait (X < 80).
        # Right of landscape (X > 700) maps to BOTTOM of portrait (Y > 700).
        # Landscape Rotate button was X: 740-810, Y > 710 -> maps to Y: 740-810, X < 120
        # Landscape Lang button was X: 830-900, Y > 710 -> maps to Y: 830-900, X < 120
        # Landscape Exit button was X: 920-990, Y > 710 -> maps to Y: 920-990, X < 120
        if touch_x < 120:
            if 730 < touch_y < 815:
                print("Action: TOGGLE")
                sys.exit(10)
            elif 820 < touch_y < 905:
                print("Action: LANG")
                sys.exit(15)
            elif touch_y >= 910:
                print("Action: EXIT")
                sys.exit(20)
    else:
        # Default Portrait (758x1024)
        # Bottom status bar is Y > 900
        if touch_y > 900:
            # Rotate button is X: 480 to 550
            # Lang button is X: 570 to 640
            # Exit button is X: 660 to 730
            if 460 < touch_x < 555:
                print("Action: TOGGLE")
                sys.exit(10)
            elif 560 < touch_x < 645:
                print("Action: LANG")
                sys.exit(15)
            elif touch_x >= 650:
                print("Action: EXIT")
                sys.exit(20)
                
    print("Action: NONE")
    sys.exit(0)

if __name__ == "__main__":
    main()
