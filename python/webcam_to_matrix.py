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

CONTRAST_GAIN = 4.0
CONTRAST_CENTER = 127
BLACK_THRESHOLD = 20  # pixels darker than this become pure black
mode = "bw"


def apply_contrast_stretch(gray):
    flat = gray.flatten().astype(np.float32)
    p_low, p_high = np.percentile(flat, [2, 98])

    if p_high > p_low:
        stretched = (gray - p_low) / (p_high - p_low) * 255.0
        stretched = np.clip(stretched, 0, 255).astype(np.uint8)
    else:
        stretched = gray

    f = (stretched.astype(np.float32) - CONTRAST_CENTER) / 127.0
    f = 1.0 / (1.0 + np.exp(-CONTRAST_GAIN * f))
    f = (f * 255.0).astype(np.uint8)

    return f


def apply_threshold(gray):
    # Otsu auto-threshold: pure black/white, no gray
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def apply_black_threshold(rgb_array):
    """Force near-black pixels to pure black to eliminate noise"""
    result = rgb_array.copy()
    for y in range(MATRIX_H):
        for x in range(MATRIX_W):
            r, g, b = int(result[y, x, 0]), int(result[y, x, 1]), int(result[y, x, 2])
            if (r + g + b) / 3.0 < BLACK_THRESHOLD:
                result[y, x] = [0, 0, 0]
    return result


def build_color_payload(rgb):
    rgb = apply_black_threshold(rgb)
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
            if v < BLACK_THRESHOLD:
                v = 0
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


def main():
    global CONTRAST_GAIN, mode, BLACK_THRESHOLD

    port = find_serial_port()
    if port is None:
        sys.exit(1)

    ser = serial.Serial(port, BAUDRATE, timeout=1)
    time.sleep(2)

    print(f"Connected: {port} @ {BAUDRATE} baud")
    print("Waiting for ESP32 to be ready...")
    time.sleep(4)
    print("\nModes: COLOR | B&W | THRESHOLD | INVERT")
    print("Keys: [m]toggle [+/-]gain [b/n]black-thresh [i]invert [q]quit\n")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Cannot open webcam.")
        ser.close()
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    frame_count = 0
    byte_count = 0
    start_time = time.time()
    fps = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            h, w = frame.shape[:2]
            pixel_size = h

            if mode == "color":
                small = cv2.resize(frame, (MATRIX_W, MATRIX_H), interpolation=cv2.INTER_AREA)
                rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                payload = build_color_payload(rgb)
                pixelated = cv2.resize(rgb, (pixel_size, pixel_size), interpolation=cv2.INTER_NEAREST)
                pixelated_bgr = cv2.cvtColor(pixelated, cv2.COLOR_RGB2BGR)
                label = "COLOR"

            elif mode == "bw":
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                small = cv2.resize(gray, (MATRIX_W, MATRIX_H), interpolation=cv2.INTER_AREA)
                boosted = apply_contrast_stretch(small)
                payload = build_gray_payload(boosted)
                pixelated = cv2.resize(boosted, (pixel_size, pixel_size), interpolation=cv2.INTER_NEAREST)
                pixelated_bgr = cv2.cvtColor(pixelated, cv2.COLOR_GRAY2BGR)
                label = "B&W"

            elif mode == "threshold":
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                small = cv2.resize(gray, (MATRIX_W, MATRIX_H), interpolation=cv2.INTER_AREA)
                binary = apply_threshold(small)
                payload = build_gray_payload(binary)
                pixelated = cv2.resize(binary, (pixel_size, pixel_size), interpolation=cv2.INTER_NEAREST)
                pixelated_bgr = cv2.cvtColor(pixelated, cv2.COLOR_GRAY2BGR)
                label = "THRESHOLD"

            elif mode == "invert":
                small = cv2.resize(frame, (MATRIX_W, MATRIX_H), interpolation=cv2.INTER_AREA)
                inv = cv2.bitwise_not(small)
                rgb = cv2.cvtColor(inv, cv2.COLOR_BGR2RGB)
                payload = build_color_payload(rgb)
                pixelated = cv2.resize(rgb, (pixel_size, pixel_size), interpolation=cv2.INTER_NEAREST)
                pixelated_bgr = cv2.cvtColor(pixelated, cv2.COLOR_RGB2BGR)
                label = "INVERT"

            packet = bytearray([SYNC_MARKER, CMD_FRAME]) + payload
            ser.write(packet)
            byte_count += len(packet)

            # Side-by-side: original (left) + pixelated (right)
            original = frame.copy()
            cv2.putText(original, "ORIGINAL", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(pixelated_bgr, f"8x8 {label}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(pixelated_bgr, f"FPS:{fps:.0f} Gain:{CONTRAST_GAIN:.1f} Black:{BLACK_THRESHOLD}", (10, h - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)

            separator = np.zeros((h, 10, 3), dtype=np.uint8)
            combined = np.hstack((original, separator, pixelated_bgr))

            cv2.putText(combined, "[m]mode [+/-]gain [b/n]black [i]invert [q]quit", (10, h + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            cv2.imshow("Webcam -> 8x8 Matrix", combined)

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
                modes = ["color", "bw", "threshold", "invert"]
                idx = modes.index(mode)
                mode = modes[(idx + 1) % len(modes)]
                print(f"Mode: {mode.upper()}")
            elif key == ord('i'):
                mode = "invert" if mode != "invert" else "bw"
                print(f"Mode: {mode.upper()}")
            elif key == ord('+') or key == ord('='):
                CONTRAST_GAIN = min(10.0, CONTRAST_GAIN + 0.5)
                print(f"Contrast gain: {CONTRAST_GAIN:.1f}")
            elif key == ord('-'):
                CONTRAST_GAIN = max(0.5, CONTRAST_GAIN - 0.5)
                print(f"Contrast gain: {CONTRAST_GAIN:.1f}")
            elif key == ord('b'):
                BLACK_THRESHOLD = min(100, BLACK_THRESHOLD + 5)
                print(f"Black threshold: {BLACK_THRESHOLD}")
            elif key == ord('n'):
                BLACK_THRESHOLD = max(0, BLACK_THRESHOLD - 5)
                print(f"Black threshold: {BLACK_THRESHOLD}")

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
