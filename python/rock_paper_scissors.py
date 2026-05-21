import cv2
import numpy as np
import mediapipe as mp
import serial
import serial.tools.list_ports
import time
import sys

MATRIX_W = 8
MATRIX_H = 8
BAUDRATE = 115200

SYNC_MARKER = 0xAA
CMD_FRAME = 0x01

ROCK = "rock"
PAPER = "paper"
SCISSORS = "scissors"
NONE = "none"

ICONS = {
    ROCK: np.array([
        [0,0,1,1,1,1,0,0],
        [0,1,1,1,1,1,1,0],
        [1,1,1,1,1,1,1,1],
        [1,1,1,1,1,1,1,1],
        [1,1,1,1,1,1,1,1],
        [1,1,1,1,1,1,1,1],
        [0,1,1,1,1,1,1,0],
        [0,0,1,1,1,1,0,0],
    ], dtype=np.uint8),

    PAPER: np.array([
        [1,1,1,1,1,1,1,1],
        [1,0,0,0,0,0,0,1],
        [1,0,1,1,1,1,0,1],
        [1,0,1,1,1,1,0,1],
        [1,0,1,1,1,1,0,1],
        [1,0,1,1,1,1,0,1],
        [1,0,0,0,0,0,0,1],
        [1,1,1,1,1,1,1,1],
    ], dtype=np.uint8),

    SCISSORS: np.array([
        [1,0,0,0,0,0,0,1],
        [1,1,0,0,0,0,1,1],
        [0,1,1,0,0,1,1,0],
        [0,0,1,1,1,1,0,0],
        [0,0,0,1,1,0,0,0],
        [0,0,1,1,1,1,0,0],
        [0,1,1,0,0,1,1,0],
        [1,1,0,0,0,0,1,1],
    ], dtype=np.uint8),
}

GESTURE_COLORS = {
    ROCK: (255, 30, 30),
    PAPER: (30, 255, 30),
    SCISSORS: (30, 130, 255),
    NONE: (0, 0, 0),
}

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles


def classify_gesture(hand_landmarks, h, w):
    tips = [8, 12, 16, 20]
    pips = [6, 10, 14, 18]
    mcp = [5, 9, 13, 17]

    fingers = []

    for tip_idx, pip_idx, mcp_idx in zip(tips, pips, mcp):
        tip_y = hand_landmarks.landmark[tip_idx].y
        pip_y = hand_landmarks.landmark[pip_idx].y

        if tip_y < pip_y:
            fingers.append(True)
        else:
            fingers.append(False)

    extended = sum(fingers)

    if extended <= 1:
        return ROCK
    elif extended == 2:
        idx = fingers.index(True) if True in fingers else -1
        idx2 = -1
        for i in range(len(fingers) - 1, -1, -1):
            if fingers[i]:
                idx2 = i
                break
        if idx == 0 and idx2 == 1:
            return SCISSORS
        return SCISSORS
    elif extended >= 4:
        return PAPER

    return ROCK


def build_payload(icon, color):
    payload = bytearray()
    for y in range(MATRIX_H):
        for x in range(MATRIX_W):
            if icon[y, x]:
                payload.extend([color[0], color[1], color[2]])
            else:
                payload.extend([0, 0, 0])
    return payload


def find_serial_port():
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("No serial ports found.")
        return None

    print("Available ports:")
    for p in ports:
        print(f"  {p.device} - {p.description}")

    for p in ports:
        if "usbmodem" in p.device.lower() or "cu.usbmodem" in p.device.lower():
            return p.device
    for p in ports:
        if "usbserial" in p.device.lower() or "cu.usbserial" in p.device.lower():
            return p.device
    for p in ports:
        if "ttyACM" in p.device.lower() or "ttyUSB" in p.device.lower():
            return p.device
    return ports[0].device


def find_camera():
    for idx in range(5):
        cap = cv2.VideoCapture(idx)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                print(f"Camera found at index {idx}")
                return cap
        cap.release()
    return None


def main():
    port = find_serial_port()
    if port is None:
        sys.exit(1)

    ser = serial.Serial(port, BAUDRATE, timeout=1)
    time.sleep(2)

    print(f"Connected: {port} @ {BAUDRATE} baud")
    print("Waiting for ESP32 to be ready...")
    time.sleep(4)
    print("Rock Paper Scissors! Show your hand. Press 'q' to quit.\n")

    cap = find_camera()
    if cap is None:
        print("Cannot open any webcam.")
        print("On macOS: grant camera permission to Terminal in")
        print("  System Preferences > Privacy & Security > Camera")
        ser.close()
        sys.exit(1)

    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.5,
    )

    gesture = NONE
    gesture_confirmed = NONE
    gesture_counter = 0
    REQUIRED_FRAMES = 5
    last_send = 0

    frame_count = 0
    start_time = time.time()
    fps = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = hands.process(rgb)
            rgb.flags.writeable = True

            h, w, _ = frame.shape
            current_gesture = NONE

            if results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    mp_drawing.draw_landmarks(
                        frame, hand_landmarks, mp_hands.HAND_CONNECTIONS,
                        mp_drawing_styles.get_default_hand_landmarks_style(),
                        mp_drawing_styles.get_default_hand_connections_style(),
                    )
                    current_gesture = classify_gesture(hand_landmarks, h, w)

            if current_gesture == gesture:
                gesture_counter += 1
            else:
                gesture = current_gesture
                gesture_counter = 1

            if gesture_counter >= REQUIRED_FRAMES:
                gesture_confirmed = gesture

            now = time.time()
            if now - last_send > 0.05:
                color = GESTURE_COLORS.get(gesture_confirmed, (0, 0, 0))
                icon = ICONS.get(gesture_confirmed, np.zeros((8, 8), dtype=np.uint8))
                payload = build_payload(icon, color)
                packet = bytearray([SYNC_MARKER, CMD_FRAME]) + payload
                ser.write(packet)
                last_send = now

            name = gesture_confirmed.upper() if gesture_confirmed != NONE else "----"
            disp_color = GESTURE_COLORS.get(gesture_confirmed, (255, 255, 255))

            cv2.putText(frame, name, (20, 50),
                        cv2.FONT_HERSHEY_DUPLEX, 1.5, disp_color, 3)
            cv2.putText(frame, f"FPS: {fps:.1f}", (20, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

            cv2.imshow("Rock Paper Scissors - Hand Gesture", frame)

            if gesture_confirmed != NONE:
                preview = np.zeros((160, 160, 3), dtype=np.uint8)
                icon = ICONS[gesture_confirmed]
                for y in range(8):
                    for x in range(8):
                        if icon[y, x]:
                            px, py = x * 20, y * 20
                            cv2.rectangle(preview, (px, py), (px + 19, py + 19),
                                          disp_color, -1)
                cv2.imshow("Matrix Preview", preview)

            frame_count += 1
            elapsed = time.time() - start_time
            if elapsed >= 1.0:
                fps = frame_count / elapsed
                frame_count = 0
                start_time = time.time()

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break

    except serial.SerialException as e:
        print(f"Serial error: {e}")
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        ser.close()
        hands.close()
        print("\nDone.")


if __name__ == "__main__":
    main()
