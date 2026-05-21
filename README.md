# ESP32-S3-Matrix Webcam & Game

Live webcam streaming and AI rock-paper-scissors game for the [Waveshare ESP32-S3-Matrix](https://www.waveshare.com/esp32-s3-matrix.htm) (8×8 RGB LED matrix).

## Hardware

- **Waveshare ESP32-S3-Matrix** (or any ESP32-S3 with WS2812 8×8 matrix)
- **USB-C cable** (data)
- **Webcam** (built-in or USB)
- **Computer** (macOS / Linux / Windows)

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/xiaoyh-code/esp32-s3-matrix.git
cd esp32-s3-matrix
```

### 2. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows
pip install opencv-python pyserial numpy mediapipe==0.10.9
```

### 3. Flash the ESP32 firmware

**Install PlatformIO** (one of these):
- **VS Code**: install the [PlatformIO IDE](https://marketplace.visualstudio.com/items?itemName=platformio.platformio-ide) extension
- **CLI**: `pip install platformio`

**Build & upload:**

```bash
cd firmware
platformio run --target upload
```

After flashing, the board reboots and runs a **startup test** (all LEDs flash Red → Green → Blue → off). This confirms the matrix works.

> **Note:** If upload fails, hold the **BOOT** button while connecting USB, or press it during the upload process.

### 4. Find your serial port

Plug in the ESP32 and run:

```bash
python -c "import serial.tools.list_ports; [print(p.device) for p in serial.tools.list_ports.comports()]"
```

Look for something like:
- macOS: `/dev/cu.usbmodem2101`
- Linux: `/dev/ttyACM0`
- Windows: `COM3`

The Python scripts auto-detect the port, but you can modify the `find_serial_port()` function in each script if needed.

---

## Scripts

### 1. Webcam → Live 8×8 Matrix

```bash
source .venv/bin/activate
python python/webcam_to_matrix.py
```

Streams your webcam to the LED matrix in real time.

| Key | Action |
|---|---|
| `m` | Toggle **Color** / **B&W** mode |
| `+` / `-` | Adjust contrast gain (B&W mode) |
| `q` | Quit |

### 2. Simple Gesture Detector

```bash
python python/rock_paper_scissors.py
```

Detects rock / paper / scissors hand gestures and displays icons on the matrix. Shows the camera feed with hand landmarks.

| Key | Action |
|---|---|
| `q` | Quit |

### 3. AI Rock Paper Scissors Game

```bash
python python/rock_paper_scissors_game.py
```

Play rock paper scissors against an AI opponent.

**Game flow:**

| Phase | Matrix display | Duration |
|---|---|---|
| Countdown | `3` → `2` → `1` | 0.8s each |
| Shoot | Captures your gesture | instant |
| Result | **W** (green) / **L** (red) / **D** (yellow) | 1.5s |
| Repeat | — | — |

The AI uses a **multi-order Markov chain** (orders 1–5) to learn your patterns:

- It remembers every sequence you play
- After `rock → paper`, it predicts what you'll play next based on past `(rock, paper)` transitions
- The more you play, the smarter it gets

**Persistent memory:** The AI saves its knowledge to `ai_brain.pkl` in the project folder and reloads it next time. Delete this file to reset the AI.

| Key | Action |
|---|---|
| `q` | Quit (shows final score) |

**On-screen info:**
- Your move, AI's move, and what the AI predicted you'd play
- Score: W(ins) / L(osses) / D(raws)

---

## Project Structure

```
esp32-s3-matrix/
├── firmware/
│   ├── platformio.ini          # PlatformIO project config
│   └── src/
│       └── main.cpp            # ESP32 firmware (Serial receiver + FastLED)
├── python/
│   ├── webcam_to_matrix.py     # Live webcam stream
│   ├── rock_paper_scissors.py  # Simple gesture detector
│   └── rock_paper_scissors_game.py  # AI game with countdown + score
├── .venv/                      # Python virtual environment
├── ai_brain.pkl                # AI's learned patterns (auto-generated)
└── README.md
```

## Customization

### Change LED brightness

Edit `firmware/src/main.cpp`:

```cpp
#define BRIGHTNESS 20   // 0–255, default is 20
```

Then re-flash: `platformio run --target upload`

### Change serial port detection

Edit the `find_serial_port()` function in any Python script to hardcode your port:

```python
def find_serial_port():
    return "/dev/cu.usbmodem2101"  # your port
```

### Change AI difficulty

Edit `MAX_ORDER` near the top of `rock_paper_scissors_game.py`:

```python
MAX_ORDER = 5   # higher = learns longer patterns
```

## Troubleshooting

| Problem | Fix |
|---|---|
| LEDs stay dark after flash | The startup test (R→G→B) should run. If not, check `LED_PIN` (default 14). |
| Python can't find serial port | Close Serial Monitor / PlatformIO terminal. Only one program can use the port at a time. |
| Webcam not opening | Try `cap = cv2.VideoCapture(1)` instead of `0`. |
| MediaPipe import error | `pip install mediapipe==0.10.9` (newer versions removed `solutions` API) |
| Gesture detection is slow | Make sure you're in a well-lit area with clear hand visibility. |
| AI keeps losing | Play at least 20 rounds — it needs data to learn your patterns. |
| Permission denied on serial port (Linux) | `sudo usermod -a -G dialout $USER` then log out and back in. |

## License

MIT
