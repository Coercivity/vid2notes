from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.imaging import apply_crop, correlation_input, estimate_shift, ink_mask, resize_to_width, to_gray
from app.messages import Crop
from app.video import PermanentError, sample_frames

PAGES_STEP = 0.5
SCROLL_STEP = 0.2
SIGNATURE_WIDTH = 400
CHANGE_THRESHOLD = 0.2
DUPLICATE_THRESHOLD = 0.1
COVER_THRESHOLD = 0.95
MIN_STABLE_SAMPLES = 2
MAX_RUN_FRAMES = 9
SHIFT_SCALE_WIDTH = 640
MIN_RESPONSE = 0.05
SYSTEM_ASPECT = 4.2

DILATE_KERNEL = np.ones((3, 3), np.uint8)


class NoNotesFoundError(PermanentError):
    pass


@dataclass
class Page:
    image: np.ndarray
    signature: np.ndarray


def _signature(image: np.ndarray) -> np.ndarray:
    ink = ink_mask(resize_to_width(to_gray(image), SIGNATURE_WIDTH))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (SIGNATURE_WIDTH // 10, 1))
    staff_lines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel)
    return (ink > 0) & ~(cv2.dilate(staff_lines, DILATE_KERNEL) > 0)


def _difference(a: np.ndarray, b: np.ndarray) -> float:
    da = cv2.dilate(a.astype(np.uint8), DILATE_KERNEL) > 0
    db = cv2.dilate(b.astype(np.uint8), DILATE_KERNEL) > 0
    changed = np.count_nonzero(a & ~db) + np.count_nonzero(b & ~da)
    total = max(np.count_nonzero(a | b), 1)
    return changed / total


def _covers(new: np.ndarray, old: np.ndarray) -> bool:
    old_ink = np.count_nonzero(old)
    if old_ink == 0:
        return True
    dilated = cv2.dilate(new.astype(np.uint8), DILATE_KERNEL) > 0
    return np.count_nonzero(old & dilated) / old_ink >= COVER_THRESHOLD


def _accept_page(pages: list[Page], candidate: Page) -> None:
    if np.count_nonzero(candidate.signature) < 50:
        return
    if any(_difference(page.signature, candidate.signature) < DUPLICATE_THRESHOLD for page in pages):
        return
    if pages and _covers(candidate.signature, pages[-1].signature):
        pages[-1] = candidate
        return
    pages.append(candidate)


def _progress(time: float, start: float, end: float) -> float:
    return min(max((time - start) / max(end - start, 0.001), 0.0), 1.0)


def extract_pages(
    path: Path,
    crop: Crop,
    start: float,
    end: float,
    on_progress: Callable[[float], None],
) -> list[np.ndarray]:
    pages: list[Page] = []
    reference: np.ndarray | None = None
    run: list[np.ndarray] = []
    seen = 0
    stride = 1

    def finish_run() -> None:
        if seen >= MIN_STABLE_SAMPLES:
            image = np.median(np.stack(run), axis=0).astype(np.uint8)
            _accept_page(pages, Page(image=image, signature=_signature(image)))

    for time, frame in sample_frames(path, PAGES_STEP, start, end):
        image = apply_crop(frame, crop)
        signature = _signature(image)
        if reference is not None and _difference(reference, signature) < CHANGE_THRESHOLD:
            seen += 1
            if seen % stride == 0:
                run.append(image.copy())
            if len(run) > MAX_RUN_FRAMES:
                run = run[::2]
                stride *= 2
        else:
            finish_run()
            reference = signature
            run = [image.copy()]
            seen = 1
            stride = 1
        on_progress(_progress(time, start, end))
    finish_run()
    return [page.image for page in pages]


class _Strip:
    def __init__(self, height: int, channels: int):
        self._canvas = np.zeros((height, 0, channels), np.uint8)
        self.width = 0

    def paste(self, image: np.ndarray, x: int) -> None:
        h, w = image.shape[:2]
        required = x + w
        if required > self._canvas.shape[1]:
            grown = np.zeros((h, max(required, self._canvas.shape[1] * 2), image.shape[2]), np.uint8)
            grown[:, : self._canvas.shape[1]] = self._canvas
            self._canvas = grown
        self._canvas[:, x:required] = image
        self.width = max(self.width, required)

    def image(self) -> np.ndarray:
        return self._canvas[:, : self.width]


def extract_scroll(
    path: Path,
    crop: Crop,
    start: float,
    end: float,
    on_progress: Callable[[float], None],
) -> list[np.ndarray]:
    strips: list[np.ndarray] = []
    strip: _Strip | None = None
    previous: np.ndarray | None = None
    window: np.ndarray | None = None
    position = 0.0
    scale = 1.0

    for time, frame in sample_frames(path, SCROLL_STEP, start, end):
        image = apply_crop(frame, crop)
        width = image.shape[1]
        current = correlation_input(image, min(width, SHIFT_SCALE_WIDTH))
        if strip is None or previous is None or window is None:
            strip = _Strip(image.shape[0], image.shape[2])
            strip.paste(image, 0)
            window = cv2.createHanningWindow(current.shape[::-1], cv2.CV_32F)
            scale = width / current.shape[1]
            position = 0.0
            previous = current
            continue

        dx, dy, response = estimate_shift(previous, current, window)
        if response < MIN_RESPONSE or abs(dy) > 3:
            if float(np.mean(np.abs(previous - current))) > 10:
                strips.append(strip.image())
                strip = _Strip(image.shape[0], image.shape[2])
                strip.paste(image, 0)
                position = 0.0
            previous = current
            continue

        if abs(dx) >= 0.5:
            position = max(0.0, position - dx * scale)
        strip.paste(image, int(round(position)))
        previous = current
        on_progress(_progress(time, start, end))

    if strip is not None:
        strips.append(strip.image())
    return [system for s in strips for system in _split_strip(s)]


def _split_strip(strip: np.ndarray) -> list[np.ndarray]:
    height, width = strip.shape[:2]
    target = max(int(height * SYSTEM_ASPECT), 200)
    if width <= target * 1.15:
        return [strip]
    ink = (ink_mask(to_gray(strip)) > 0).sum(axis=0)
    systems = []
    x = 0
    while width - x > target * 1.15:
        lo, hi = x + int(target * 0.85), x + target
        cut = lo + int(np.argmin(ink[lo:hi]))
        systems.append(strip[:, x:cut])
        x = cut
    systems.append(strip[:, x:])
    return systems


def extract(
    path: Path,
    crop: Crop,
    layout: str,
    start: float,
    end: float,
    on_progress: Callable[[float], None],
) -> list[np.ndarray]:
    extractor = extract_scroll if layout == "scroll" else extract_pages
    fragments = extractor(path, crop, start, end, on_progress)
    if not fragments:
        raise NoNotesFoundError("No sheet music found in the selected region")
    return fragments
