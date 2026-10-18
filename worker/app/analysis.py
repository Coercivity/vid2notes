from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from app.imaging import correlation_input, estimate_shift, resize_to_width, to_gray
from app.keyboard import Keyboard, detect_keyboard
from app.messages import Crop
from app.video import VideoInfo, sample_frames

DETECTION_WIDTH = 960
CORRELATION_WIDTH = 480
PREVIEW_COUNT = 6
MAX_SAMPLES = 600
FULL_FRAME = Crop(x=0.0, y=0.0, width=1.0, height=1.0)
KEYBOARD_SHARE = 0.5


@dataclass(frozen=True)
class Staff:
    x0: int
    y0: int
    x1: int
    y1: int
    spacing: float


@dataclass
class AnalysisResult:
    crop: Crop
    layout: str
    previews: list[bytes] = field(default_factory=list)


def _horizontal_lines(gray: np.ndarray) -> np.ndarray:
    mask = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 15)
    length = max(gray.shape[1] // 12, 10)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (length, 1))
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)


def find_staves(gray: np.ndarray) -> list[Staff]:
    return max(_find_staves(gray), _find_staves(255 - gray), key=len)


def _find_staves(gray: np.ndarray) -> list[Staff]:
    width = gray.shape[1]
    lines_mask = _horizontal_lines(gray) > 0
    coverage = lines_mask.sum(axis=1) / width
    rows = np.flatnonzero(coverage > 0.08)
    if rows.size == 0:
        return []

    max_thickness = max(4, width // 240)
    lines: list[tuple[float, int, int]] = []
    start = previous = rows[0]
    for row in [*rows[1:], None]:
        if row is not None and row - previous <= 1:
            previous = row
            continue
        if previous - start + 1 <= max_thickness:
            columns = np.flatnonzero(lines_mask[start : previous + 1].any(axis=0))
            lines.append(((start + previous) / 2, int(columns.min()), int(columns.max())))
        if row is not None:
            start = previous = row

    staves: list[Staff] = []
    i = 0
    while i + 5 <= len(lines):
        group = lines[i : i + 5]
        gaps = np.diff([line[0] for line in group])
        spacing = float(np.median(gaps))
        if spacing >= 3 and np.all(np.abs(gaps - spacing) <= max(1.5, 0.25 * spacing)):
            staves.append(
                Staff(
                    x0=min(line[1] for line in group),
                    y0=int(group[0][0]),
                    x1=max(line[2] for line in group),
                    y1=int(group[-1][0]),
                    spacing=spacing,
                )
            )
            i += 5
        else:
            i += 1
    return staves


def _frame_region(staves: list[Staff], width: int, height: int) -> tuple[float, float, float, float]:
    spacing = float(np.median([s.spacing for s in staves]))
    x0 = max(0.0, min(s.x0 for s in staves) - spacing)
    x1 = min(float(width), max(s.x1 for s in staves) + spacing)
    y0 = max(0.0, min(s.y0 for s in staves) - 5 * spacing)
    y1 = min(float(height), max(s.y1 for s in staves) + 5 * spacing)
    return x0 / width, y0 / height, x1 / width, y1 / height


def _suggest_crop(regions: list[tuple[float, float, float, float]]) -> Crop:
    if not regions:
        return FULL_FRAME
    values = np.array(regions)
    x0 = float(np.percentile(values[:, 0], 10))
    y0 = float(np.percentile(values[:, 1], 10))
    x1 = float(np.percentile(values[:, 2], 90))
    y1 = float(np.percentile(values[:, 3], 90))
    if x1 - x0 < 0.05 or y1 - y0 < 0.05:
        return FULL_FRAME
    return Crop(x=round(x0, 4), y=round(y0, 4), width=round(x1 - x0, 4), height=round(y1 - y0, 4))


def _classify_layout(frames: list[np.ndarray]) -> str:
    if len(frames) < 4:
        return "pages"
    window = cv2.createHanningWindow(frames[0].shape[::-1], cv2.CV_32F)
    moving = 0
    scrolling = 0
    for previous, current in zip(frames, frames[1:]):
        if float(np.mean(np.abs(previous - current))) < 2.0:
            continue
        moving += 1
        dx, dy, response = estimate_shift(previous, current, window)
        if abs(dx) >= 2 and abs(dy) < 2 and response > 0.1:
            scrolling += 1
    return "scroll" if scrolling >= 3 and scrolling >= 0.4 * moving else "pages"


def _keyboard_crop(keyboards: list[Keyboard], info: VideoInfo) -> Crop:
    top = float(np.median([k.top for k in keyboards]))
    bottom = float(np.median([k.bottom for k in keyboards]))
    left = float(np.median([k.left for k in keyboards]))
    right = float(np.median([k.right for k in keyboards]))
    margin = (bottom - top) * 0.05
    y0 = max(0.0, top - margin) / info.height
    y1 = min(float(info.height), bottom + margin) / info.height
    x0 = max(0.0, left - margin) / info.width
    x1 = min(float(info.width), right + 1 + margin) / info.width
    return Crop(x=round(x0, 4), y=round(y0, 4), width=round(x1 - x0, 4), height=round(y1 - y0, 4))


def analyze(path: Path, info: VideoInfo, on_progress: Callable[[float], None]) -> AnalysisResult:
    duration = max(info.duration, 0.001)
    step = max(0.5, duration / MAX_SAMPLES)
    preview_times = [duration * (i + 0.5) / PREVIEW_COUNT for i in range(PREVIEW_COUNT)]

    regions: list[tuple[float, float, float, float]] = []
    samples: list[np.ndarray] = []
    previews: list[bytes] = []
    keyboards: list[Keyboard] = []

    for time, frame in sample_frames(path, step):
        keyboard = detect_keyboard(frame)
        if keyboard is not None:
            keyboards.append(keyboard)
        gray = resize_to_width(to_gray(frame), DETECTION_WIDTH)
        staves = find_staves(gray)
        if staves:
            regions.append(_frame_region(staves, gray.shape[1], gray.shape[0]))
        samples.append(resize_to_width(frame, CORRELATION_WIDTH))
        if len(previews) < PREVIEW_COUNT and time >= preview_times[len(previews)]:
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                previews.append(encoded.tobytes())
        on_progress(min(time / duration, 1.0))

    if samples and len(keyboards) >= KEYBOARD_SHARE * len(samples):
        return AnalysisResult(crop=_keyboard_crop(keyboards, info), layout="synthesia", previews=previews)

    crop = _suggest_crop(regions)
    cropped = []
    for sample in samples:
        h, w = sample.shape[:2]
        x0, y0 = int(crop.x * w), int(crop.y * h)
        x1, y1 = max(x0 + 1, int((crop.x + crop.width) * w)), max(y0 + 1, int((crop.y + crop.height) * h))
        region = sample[y0:y1, x0:x1]
        cropped.append(correlation_input(region, region.shape[1]))
    layout = _classify_layout(cropped)
    return AnalysisResult(crop=crop, layout=layout, previews=previews)
