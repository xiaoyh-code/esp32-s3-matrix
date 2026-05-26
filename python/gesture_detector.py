import cv2
import numpy as np
import mediapipe as mp
import serial
import serial.tools.list_ports
import time
import sys

BAUDRATE = 115200
SYNC_MARKER = 0xAA
CMD_FRAME = 0x01

ROCK, PAPER, SCISSORS, NONE = "rock", "paper", "scissors", "none"
GESTURE_COLORS = {
    ROCK: (30, 30, 255),
    PAPER: (30, 255, 30),
    SCISSORS: (255, 160, 30),
}


def find_serial_port():
    for p in serial.tools.list_ports.comports():
        if "usbmodem" in p.device.lower() or "usbserial" in p.device.lower():
            return p.device
    for p in serial.tools.list_ports.comports():
        if "ttyACM" in p.device.lower() or "ttyUSB" in p.device.lower():
            return p.device
    return None


def detect_gesture(landmarks):
    tips = [8, 12, 16, 20]
    pips = [6, 10, 14, 18]
    extended = 0
    for tip_idx, pip_idx in zip(tips, pips):
        if landmarks.landmark[tip_idx].y < landmarks.landmark[pip_idx].y:
            extended += 1
    if extended <= 1:
        return ROCK
    elif extended == 2:
        return SCISSORS
    elif extended >= 4:
        return PAPER
    return ROCK


def send_gesture(ser, gesture):
    if not ser:
        return
    color = GESTURE_COLORS.get(gesture, (50, 50, 50))
    payload = bytearray()
    for _ in range(64):
        payload.extend([color[2], color[1], color[0]])
    ser.write(bytearray([SYNC_MARKER, CMD_FRAME]) + payload)


def main():
    port = find_serial_port()
    ser = serial.Serial(port, BAUDRATE, timeout=1) if port else None
    if ser:
        time.sleep(2)
        print(f"ESP32: {port}")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("\nCamera blocked by macOS.")
        print("FIX: double-click CameraFix.app on Desktop, click Allow.")
        if ser: ser.close()
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    print("Camera OK. Show your hand. [Q] to quit.\n")

    mp_hands = mp.solutions.hands
    mp_drawing = mp.solutions.drawing_utils
    mp_drawing_styles = mp.solutions.drawing_styles

    hands = mp_hands.Hands(
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.5,
        model_complexity=1,
    )

    current_gesture = NONE
    frame_count = 0
    t0 = time.time()

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
            gesture = NONE

            if results.multi_hand_landmarks:
                for hl in results.multi_hand_landmarks:
                    mp_drawing.draw_landmarks(
                        frame, hl, mp_hands.HAND_CONNECTIONS,
                        mp_drawing_styles.get_default_hand_landmarks_style(),
                        mp_drawing_styles.get_default_hand_connections_style(),
                    )
                    gesture = detect_gesture(hl)
                    current_gesture = gesture

            if current_gesture != NONE:
                name = current_gesture.upper()
                color = GESTURE_COLORS.get(current_gesture, (255, 255, 255))
                cv2.putText(frame, name, (20, 50),
                            cv2.FONT_HERSHEY_DUPLEX, 1.5, color, 3)
                send_gesture(ser, current_gesture)

            fps = int(frame_count / max(time.time() - t0, 0.01))
            cv2.putText(frame, f"FPS:{fps}  [Q]uit", (w - 150, h - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

            cv2.imshow("Rock Paper Scissors - Gesture Detector", frame)

            frame_count += 1
            if frame_count % 30 == 0:
                frame_count = 0
                t0 = time.time()

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        if ser: ser.close()
        hands.close()
        print("Done.")


if __name__ == "__main__":
    main()
