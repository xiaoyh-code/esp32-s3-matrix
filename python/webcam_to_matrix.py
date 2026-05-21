import cv2
import numpy as np
import serial
import serial.tools.list_ports
import time
import sys

MATRIX_W = 8
MATRIX_H = 8
BAUDRATE = 115200

SYNC_MARKER = 0xAA
CMD_FRAME = 0x01

CONTRAST_GAIN = 2.5
CONTRAST_CENTER = 127
mode = "color"


def apply_contrast_stretch(gray):
    flat = gray.flatten().astype(np.float32)

    p_low, p_high = np.percentile(flat, [5, 95])

    if p_high > p_low:
        stretched = (gray - p_low) / (p_high - p_low) * 255.0
        stretched = np.clip(stretched, 0, 255).astype(np.uint8)
    else:
        stretched = gray

    f = (stretched.astype(np.float32) - CONTRAST_CENTER) / 127.0
    f = 1.0 / (1.0 + np.exp(-CONTRAST_GAIN * f))
    f = (f * 255.0).astype(np.uint8)

    return f


def build_color_payload(rgb):
    payload = bytearray()
    for y in range(MATRIX_H):
        for x in range(MATRIX_W):
            rr, gg, bb = int(rgb[y, x, 0]), int(rgb[y, x, 1]), int(rgb[y, x, 2])
            payload.extend([rr, gg, bb])
    return payload


def build_gray_payload(boosted):
    payload = bytearray()
    for y in range(MATRIX_H):
        for x in range(MATRIX_W):
            v = int(boosted[y, x])
            payload.extend([v, v, v])
    return payload


def find_serial_port():
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("No serial ports found. Is the ESP32 connected?")
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
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                print(f"Camera found at index {idx}")
                return cap
        cap.release()
    return None


def main():
    global CONTRAST_GAIN, mode

    port = find_serial_port()
    if port is None:
        sys.exit(1)

    ser = serial.Serial(port, BAUDRATE, timeout=1)
    time.sleep(2)

    print(f"Connected: {port} @ {BAUDRATE} baud")
    print("Waiting for ESP32 to be ready...")
    time.sleep(4)
    print("Mode: COLOR  |  Keys: [m] toggle mode  [q] quit  [+/-] contrast")
    print("Starting stream...")

    cap = find_camera()
    if cap is None:
        print("Cannot open any webcam.")
        print("On macOS: grant camera permission to Terminal in")
        print("  System Preferences > Privacy & Security > Camera")
        ser.close()
        sys.exit(1)

    frame_count = 0
    byte_count = 0
    start_time = time.time()
    fps = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if mode == "color":
                small = cv2.resize(frame, (MATRIX_W, MATRIX_H), interpolation=cv2.INTER_AREA)
                rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                payload = build_color_payload(rgb)
                disp = cv2.resize(rgb, (320, 320), interpolation=cv2.INTER_NEAREST)
                disp_bgr = cv2.cvtColor(disp, cv2.COLOR_RGB2BGR)
                label = "COLOR"
            else:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                small = cv2.resize(gray, (MATRIX_W, MATRIX_H), interpolation=cv2.INTER_AREA)
                boosted = apply_contrast_stretch(small)
                payload = build_gray_payload(boosted)
                disp = cv2.resize(boosted, (320, 320), interpolation=cv2.INTER_NEAREST)
                disp_bgr = cv2.cvtColor(disp, cv2.COLOR_GRAY2BGR)
                label = "B&W"

            packet = bytearray([SYNC_MARKER, CMD_FRAME]) + payload
            ser.write(packet)
            byte_count += len(packet)

            cv2.putText(disp_bgr, f"{label} | FPS: {fps:.1f} | Gain: {CONTRAST_GAIN:.1f}",
                        (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
            cv2.putText(disp_bgr, "[m] mode  [+/-] contrast  [q] quit",
                        (5, 310), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 100), 1)
            cv2.imshow("Webcam -> 8x8 Matrix", disp_bgr)

            frame_count += 1
            elapsed = time.time() - start_time
            if elapsed >= 1.0:
                fps = frame_count / elapsed
                frame_count = 0
                start_time = time.time()

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('m'):
                mode = "bw" if mode == "color" else "color"
                print(f"Mode switched to: {mode.upper()}")
            elif key == ord('+') or key == ord('='):
                CONTRAST_GAIN = min(10.0, CONTRAST_GAIN + 0.5)
                print(f"Contrast gain: {CONTRAST_GAIN:.1f}")
            elif key == ord('-'):
                CONTRAST_GAIN = max(0.5, CONTRAST_GAIN - 0.5)
                print(f"Contrast gain: {CONTRAST_GAIN:.1f}")

    except serial.SerialException as e:
        print(f"Serial error: {e}")
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        ser.close()
        print(f"\nDone. Sent {byte_count} bytes total.")


if __name__ == "__main__":
    main()
