import serial
import serial.tools.list_ports
import time
import sys
import random
import threading
from pynput import keyboard

MATRIX_W = 8
MATRIX_H = 8
BAUDRATE = 115200

SYNC_MARKER = 0xAA
CMD_FRAME = 0x01

PLAYER_COLOR = (0, 80, 255)
TARGET_COLOR = (255, 30, 30)
WALL_COLOR = (60, 60, 60)
BG_COLOR = (0, 0, 0)

keys_pressed = set()
lock = threading.Lock()
running = True


def on_press(key):
    global running
    try:
        k = key.char.lower() if hasattr(key, 'char') and key.char else None
        with lock:
            if k == 'q':
                running = False
            elif k in ('w', 'a', 's', 'd'):
                keys_pressed.add(k)
    except AttributeError:
        if key == keyboard.Key.esc:
            running = False


def on_release(key):
    try:
        k = key.char.lower() if hasattr(key, 'char') and key.char else None
        with lock:
            keys_pressed.discard(k)
    except AttributeError:
        pass


def find_serial_port():
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if "usbmodem" in p.device.lower():
            return p.device
    for p in ports:
        if "usbserial" in p.device.lower():
            return p.device
    for p in ports:
        if "ttyACM" in p.device.lower() or "ttyUSB" in p.device.lower():
            return p.device
    return ports[0].device if ports else None


def build_payload(grid):
    payload = bytearray()
    for y in range(MATRIX_H):
        for x in range(MATRIX_W):
            r, g, b = grid[y][x]
            payload.extend([r, g, b])
    return payload


def send_frame(ser, grid):
    packet = bytearray([SYNC_MARKER, CMD_FRAME]) + build_payload(grid)
    ser.write(packet)


def new_target(exclude):
    while True:
        x = random.randint(0, MATRIX_W - 1)
        y = random.randint(0, MATRIX_H - 1)
        if (x, y) != exclude:
            return (x, y)


def render_grid(px, py, tx, ty):
    grid = [[BG_COLOR for _ in range(MATRIX_W)] for _ in range(MATRIX_H)]
    grid[ty][tx] = TARGET_COLOR
    grid[py][px] = PLAYER_COLOR
    return grid


def draw_terminal(grid, score, fps):
    sys.stdout.write("\033[H")
    sys.stdout.write(f"  WASD=move  Q=quit  Score: {score:03d}  FPS: {fps}\n")
    sys.stdout.write("  +" + "--" * MATRIX_W + "+\n")
    for y in range(MATRIX_H):
        sys.stdout.write(f"  |")
        for x in range(MATRIX_W):
            r, g, b = grid[y][x]
            if (r, g, b) == PLAYER_COLOR:
                c = "\033[34m██\033[0m"
            elif (r, g, b) == TARGET_COLOR:
                c = "\033[31m██\033[0m"
            elif (r, g, b) != BG_COLOR:
                c = "\033[90m██\033[0m"
            else:
                c = "  "
            sys.stdout.write(c)
        sys.stdout.write("|\n")
    sys.stdout.write("  +" + "--" * MATRIX_W + "+\n")
    sys.stdout.flush()


def main():
    global running

    port = find_serial_port()
    ser = None
    if port:
        ser = serial.Serial(port, BAUDRATE, timeout=1)
        time.sleep(2)
        print(f"Connected: {port}")
        print("Waiting for ESP32...")
        time.sleep(3)
    else:
        print("No ESP32 found. Terminal-only mode.\n")

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    px, py = MATRIX_W // 2, MATRIX_H // 2
    tx, ty = new_target((px, py))
    score = 0
    move_interval = 0.12
    last_move = time.time()

    print("\033[2J\033[H")
    print("   WASD GAME — control the blue dot on ESP32 matrix!\n")

    frame_count = 0
    t0 = time.time()

    try:
        while running:
            now = time.time()

            if now - last_move >= move_interval:
                with lock:
                    key_set = keys_pressed.copy()

                if 'w' in key_set and py > 0:
                    py -= 1
                if 's' in key_set and py < MATRIX_H - 1:
                    py += 1
                if 'a' in key_set and px > 0:
                    px -= 1
                if 'd' in key_set and px < MATRIX_W - 1:
                    px += 1
                last_move = now

            if (px, py) == (tx, ty):
                score += 1
                tx, ty = new_target((px, py))

            grid = render_grid(px, py, tx, ty)

            if ser:
                send_frame(ser, grid)

            frame_count += 1
            if frame_count % 5 == 0:
                fps = int(frame_count / max(now - t0, 0.01))
                draw_terminal(grid, score, fps)

            time.sleep(0.02)

    except serial.SerialException as e:
        print(f"\nSerial error: {e}")
    except KeyboardInterrupt:
        pass
    finally:
        running = False
        listener.stop()
        if ser:
            ser.close()
        sys.stdout.write("\033[2J\033[H")
        print(f"Score: {score}")
        print("Done.")


if __name__ == "__main__":
    main()
