import serial
import serial.tools.list_ports
import time
import sys
import random
import os
import threading
from pynput import keyboard

BAUDRATE = 115200
SYNC_MARKER, CMD_FRAME = 0xAA, 0x01

PLAYER = (0, 80, 255)
TARGET = (255, 30, 30)
OBSTACLE = (60, 60, 60)
BG = (0, 0, 0)

keys_pressed = set()
lock = threading.Lock()


def on_press(key):
    try:
        k = key.char.lower() if hasattr(key, 'char') and key.char else None
        with lock:
            if k in ('w','a','s','d'):
                keys_pressed.add(k)
    except:
        pass


def on_release(key):
    try:
        k = key.char.lower() if hasattr(key, 'char') and key.char else None
        with lock:
            keys_pressed.discard(k)
    except:
        pass


def find_port():
    for p in serial.tools.list_ports.comports():
        if any(x in p.device.lower() for x in ("usbmodem","usbserial","ttyacm","ttyusb")):
            return p.device
    return None


def send(ser, grid):
    if not ser: return
    b = bytearray([SYNC_MARKER, CMD_FRAME])
    for y in range(8):
        for x in range(8):
            r,g,bl = grid[y][x]
            b.extend([bl,g,r])
    ser.write(b)


def new_target(px,py,obstacles):
    while True:
        x,y = random.randint(0,7), random.randint(0,7)
        if (x,y) != (px,py) and (x,y) not in obstacles:
            return (x,y)


def main():
    port = find_port()
    ser = serial.Serial(port, BAUDRATE, timeout=1) if port else None
    if ser:
        time.sleep(2)
        print(f"ESP32: {port}")
        time.sleep(2)
    else:
        print("ESP32 not found — terminal-only mode.")

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    px, py = 3, 3
    score = 0
    level = 1
    obstacles = set()
    tx, ty = new_target(px, py, obstacles)
    lives = 3

    move_interval = 0.15
    last_move = time.time()

    print("\n  WASD GAME")
    print("  Blue dot = you | Red = target | Gray = wall")
    print("  Collect red targets. Avoid walls.")
    print("  [WASD] move | [Q] quit\n")

    try:
        while lives > 0:
            now = time.time()

            if now - last_move >= move_interval:
                with lock:
                    ks = keys_pressed.copy()

                if 'w' in ks and py > 0: py -= 1
                if 's' in ks and py < 7: py += 1
                if 'a' in ks and px > 0: px -= 1
                if 'd' in ks and px < 7: px += 1
                last_move = now

            # Check collision with obstacle
            if (px, py) in obstacles:
                lives -= 1
                px, py = 3, 3
                obstacles.clear()
                tx, ty = new_target(px, py, obstacles)
                print(f"  HIT WALL! Lives: {lives}")
                if lives == 0:
                    break

            # Collect target
            if (px, py) == (tx, ty):
                score += 10 * level
                level = min(5, score // 50 + 1)
                # Add obstacle every 2 levels
                if level > len(obstacles) // 2:
                    while True:
                        ox, oy = random.randint(0,7), random.randint(0,7)
                        if (ox,oy) not in obstacles and (ox,oy) != (px,py):
                            obstacles.add((ox,oy))
                            break
                tx, ty = new_target(px, py, obstacles)
                print(f"  Score: {score}  Level: {level}")

            # Build grid
            grid = [[BG for _ in range(8)] for _ in range(8)]
            for ox, oy in obstacles:
                grid[oy][ox] = OBSTACLE
            grid[ty][tx] = TARGET
            grid[py][px] = PLAYER

            if ser:
                send(ser, grid)

            # Terminal display
            sys.stdout.write("\033[H")
            sys.stdout.write(f"  Score: {score:03d}  Level: {level}  Lives: {lives}  [Q]uit\n")
            sys.stdout.write("  +" + "--"*8 + "+\n")
            for y in range(8):
                sys.stdout.write("  |")
                for x in range(8):
                    r,g,b = grid[y][x]
                    if (x,y) == (px,py):
                        sys.stdout.write("\033[34m██\033[0m")
                    elif (x,y) == (tx,ty):
                        sys.stdout.write("\033[31m██\033[0m")
                    elif (r,g,b) != BG:
                        sys.stdout.write("\033[90m██\033[0m")
                    else:
                        sys.stdout.write("  ")
                sys.stdout.write("|\n")
            sys.stdout.write("  +" + "--"*8 + "+\n")
            sys.stdout.flush()

            if 'q' in keys_pressed:
                break

            time.sleep(0.03)

    except KeyboardInterrupt:
        pass
    finally:
        listener.stop()
        if ser: ser.close()
        sys.stdout.write("\033[2J\033[H")
        print(f"Final Score: {score}  Level: {level}")
        print("Done.")


if __name__ == "__main__":
    main()
