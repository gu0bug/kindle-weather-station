# Kindle Typographic Weather Dashboard

[![License](https://img.shields.io/github/license/gu0bug/kindle-weather-station)](LICENSE)
[![GitHub release (latest by date)](https://img.shields.io/github/v/release/gu0bug/kindle-weather-station?color=blue)](https://github.com/gu0bug/kindle-weather-station/releases)
[![GitHub repo size](https://img.shields.io/github/repo-size/gu0bug/kindle-weather-station)](https://github.com/gu0bug/kindle-weather-station)
![Platform](https://img.shields.io/badge/Platform-Kindle-orange)
![KUAL](https://img.shields.io/badge/KUAL-Supported-brightgreen)
[![GitHub stars](https://img.shields.io/github/stars/gu0bug/kindle-weather-station?style=social)](https://github.com/gu0bug/kindle-weather-station/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/gu0bug/kindle-weather-station?style=social)](https://github.com/gu0bug/kindle-weather-station/network/members)

This KUAL extension turns a jailbroken Amazon Kindle into a low-power, standalone time and weather station display. Utilizing a robust **Python Pillow (PIL)** script (`render.py`), it programmatically draws a high-contrast layout, complete with 7-segment clock digits, custom vector weather icons, and metadata in English and Chinese.

The dashboard includes a touchscreen-controlled status bar with buttons to switch layout orientation, toggle between English and Chinese translation, and exit back to the Kindle reader GUI.

---

## Screenshots

| Portrait Mode (Default) | Landscape Mode |
|---|---|
| ![Portrait Mode](images/portrait.jpg) | ![Landscape Mode](images/landscape.jpg) |

---

## Features

- **Dual Layouts**: Supports **Portrait** (758x1024, default) and **Landscape** (1024x758, rotated 90 degrees clockwise to fit the portrait framebuffer).
- **Dual Languages**: Dynamically toggles between **Chinese** and **English** (dates, weekdays, weather descriptions, and buttons).
- **LCD Clock**: Renders a giant digital clock using custom chamfered 7-segment segment vectors (no external font files required).
- **Heartbeat Colon**: The clock colon ":" blinks dynamically (shows for 7 seconds, disappears for 3 seconds of every 10-second cycle).
- **Clean Grayscale Icons**: Renders minimalist vector weather icons on-the-fly.
- **Fast Interactive Response**: Orientation and language switching takes less than a second using a local weather forecast cache.
- **Auto-Exit**: Daemon terminates and restores the Kindle GUI immediately upon USB charging or connection to a PC.
- **Author Signature**: Renders `" by Gu0 Qiang"` centered at the bottom of the status bar.

---

## Hardware & Software Requirements

1. **Jailbroken Kindle**: Touch-capable e-ink Kindle (such as Paperwhite 2/3/4, Voyage, Oasis, etc.).
2. **KUAL (Kindle Unified Application Launcher)**: To launch the script.
3. **Python 3 Package**: Installed on your Kindle under `/mnt/us/python3` (specifically Python 3.9+ with `Pillow` library).
4. **Internet Connection**: Kindle must be configured to connect to your local Wi-Fi.

---

## File Structure

```text
weather-station/
├── config.xml         # KUAL extension definition
├── menu.json          # KUAL launcher menu
├── weather.sh         # Main automation loop & power daemon (shell script)
├── render.py          # Python Pillow layout rendering script
├── monitor_touch.py   # Touchscreen input binary decoder daemon
└── images/            # Screenshots and project media
```

---

## Installation & Configuration

1. **OpenWeatherMap API Key**: Sign up at [OpenWeatherMap](https://openweathermap.org/) to get a free API key.
2. **Configure weather.sh**:
   Open `weather.sh` and fill in your details:
   ```bash
   API_KEY="YOUR_OPENWEATHERMAP_API_KEY"
   CITY_NAME="Shanghai,CN"
   INTERVAL=600  # Wake up and update every 10 minutes (600 seconds)
   ```
3. **Deploy to Kindle**:
   - Connect your Kindle to your PC via USB.
   - Copy the `weather-station` directory into the `extensions` folder on your Kindle's root directory:
     `[Kindle Root]/extensions/weather-station/`
   - **Crucial**: Ensure all files (especially `weather.sh` and python scripts) use **Unix (LF) line endings**. If you copy files from Windows, verify line endings are not converted to CRLF.

---

## Usage

1. Eject your Kindle safely from your computer.
2. Open **KUAL** on the device.
3. Tap **Weather Station** -> **Start Weather Station**.
4. The dashboard will launch and update automatically.
5. Tap **中/EN** to switch between languages, **Rotate** / **旋转** to change the orientation, or **Exit** / **退出** to quit the dashboard and return to the Kindle home screen.

---

## License

This project is open-source and free to use. Customized by **Gu0 Qiang**.
