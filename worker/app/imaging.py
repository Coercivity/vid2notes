import cv2
import numpy as np

from app.messages import Crop


def to_gray(frame: np.ndarray) -> np.ndarray:
    return frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def resize_to_width(image: np.ndarray, width: int) -> np.ndarray:
    h, w = image.shape[:2]
    if w == width:
        return image
    height = max(1, round(h * width / w))
    interpolation = cv2.INTER_AREA if width < w else cv2.INTER_CUBIC
    return cv2.resize(image, (width, height), interpolation=interpolation)


def is_dark(gray: np.ndarray) -> bool:
    return float(np.median(gray)) < 110


def ink_mask(gray: np.ndarray) -> np.ndarray:
    if is_dark(gray):
        gray = 255 - gray
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 15)


def crop_pixels(crop: Crop, width: int, height: int) -> tuple[int, int, int, int]:
    x0 = int(np.clip(round(crop.x * width), 0, width - 1))
    y0 = int(np.clip(round(crop.y * height), 0, height - 1))
    x1 = int(np.clip(round((crop.x + crop.width) * width), x0 + 1, width))
    y1 = int(np.clip(round((crop.y + crop.height) * height), y0 + 1, height))
    return x0, y0, x1, y1


def apply_crop(frame: np.ndarray, crop: Crop) -> np.ndarray:
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = crop_pixels(crop, w, h)
    return frame[y0:y1, x0:x1]


def _trim_dark_border(fragment: np.ndarray) -> np.ndarray:
    gray = to_gray(fragment)
    dark = gray < 110
    rows = np.flatnonzero(dark.mean(axis=1) < 0.6)
    columns = np.flatnonzero(dark.mean(axis=0) < 0.6)
    if rows.size == 0 or columns.size == 0:
        return fragment
    return fragment[rows[0] : rows[-1] + 1, columns[0] : columns[-1] + 1]


def normalize_paper(fragment: np.ndarray) -> np.ndarray:
    if is_dark(to_gray(fragment)):
        fragment = cv2.bitwise_not(fragment)
    return _trim_dark_border(fragment)


def estimate_shift(previous: np.ndarray, current: np.ndarray, window: np.ndarray) -> tuple[float, float, float]:
    (dx, dy), response = cv2.phaseCorrelate(previous, current, window)
    return dx, dy, response


def correlation_input(frame: np.ndarray, width: int) -> np.ndarray:
    return resize_to_width(to_gray(frame), width).astype(np.float32)
