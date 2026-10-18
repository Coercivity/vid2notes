from dataclasses import dataclass

import cv2
import numpy as np

from app.imaging import to_gray

MIN_CONTRAST = 40
WHITE_SHARE = 0.6
WHITE_LEVEL = 0.2
LOCAL_WINDOW = 0.04
LOCAL_MARGIN = 8.0
LOCAL_MARGIN_SHARE = 0.2
MIN_BLACK_KEYS = 12
MIN_BAND_ROWS = 5
BLACK_PITCH_CLASSES = {1, 3, 6, 8, 10}
WHITE_STEPS = (0, 2, 4, 5, 7, 9, 11)
BLACK_OFFSETS = {1: 1, 3: 2, 6: 4, 8: 5, 10: 6}
KNOWN_LOWEST_PITCH = {52: 21, 45: 28, 36: 36, 29: 36}


@dataclass(frozen=True)
class Key:
    pitch: int
    x: float
    black: bool


@dataclass(frozen=True)
class Band:
    top: int
    black_row: int
    white_row: int
    bottom: int
    black_keys: int
    threshold: float


@dataclass(frozen=True)
class Keyboard:
    top: int
    bottom: int
    left: int
    right: int
    black_row: int
    white_row: int
    white_width: float
    keys: tuple[Key, ...]

    @property
    def lowest(self) -> int:
        return min(k.pitch for k in self.keys)

    @property
    def highest(self) -> int:
        return max(k.pitch for k in self.keys)


def _longest_run(mask: np.ndarray, max_gap: int = 0) -> tuple[int, int] | None:
    indices = np.flatnonzero(mask)
    if indices.size == 0:
        return None
    best = (indices[0], indices[0])
    start = previous = indices[0]
    for index in indices[1:]:
        if index - previous > max_gap + 1:
            if previous - start > best[1] - best[0]:
                best = (start, previous)
            start = index
        previous = index
    if previous - start > best[1] - best[0]:
        best = (start, previous)
    return int(best[0]), int(best[1])


def _local_dark(rows: np.ndarray) -> np.ndarray:
    values = rows.astype(np.float32)
    size = max(9, round(values.shape[1] * LOCAL_WINDOW))
    contrast = np.percentile(values, 90, axis=1) - np.percentile(values, 10, axis=1)
    margin = np.maximum(LOCAL_MARGIN, LOCAL_MARGIN_SHARE * contrast)[:, None]
    return values < cv2.blur(values, (size, 1)) - margin


def find_band(gray: np.ndarray, search_from: int = 0) -> Band | None:
    offset = search_from
    region = gray[offset:].astype(np.float32)
    low = np.percentile(region, 10, axis=1)
    high = np.percentile(region, 90, axis=1)
    dark = _local_dark(region)
    fraction = 1.0 - dark.mean(axis=1)
    width = max(3, round(gray.shape[1] / 400))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (width, 1))
    wide_dark = cv2.morphologyEx(dark.astype(np.uint8), cv2.MORPH_OPEN, kernel) > 0
    dark_runs = (wide_dark[:, 1:] & ~wide_dark[:, :-1]).sum(axis=1)

    black_rows = (
        (dark_runs >= MIN_BLACK_KEYS)
        & (fraction > 0.3)
        & (fraction < 0.9)
        & (high - low >= MIN_CONTRAST)
    )
    band = _longest_run(black_rows, max_gap=1)
    if band is None or band[1] - band[0] + 1 < MIN_BAND_ROWS:
        return None
    top, black_end = band
    dark_level = float(np.median(low[top : black_end + 1]))
    light_level = float(np.median(high[top : black_end + 1]))
    threshold = dark_level + WHITE_LEVEL * (light_level - dark_level)

    white_rows = (region > threshold).mean(axis=1) > WHITE_SHARE
    white_rows[: black_end + 1] = False
    white = _longest_run(white_rows, max_gap=2)
    if white is None or white[0] - black_end > (black_end - top) or white[1] - white[0] < 2:
        return None

    black_row = top + int((black_end - top) * 0.65)
    return Band(
        top=top + offset,
        black_row=black_row + offset,
        white_row=(white[0] + white[1]) // 2 + offset,
        bottom=white[1] + offset,
        black_keys=int(np.median(dark_runs[top : black_end + 1])),
        threshold=threshold,
    )


def _dark_run_centers(row: np.ndarray) -> np.ndarray:
    bright = ~_local_dark(row.reshape(1, -1))[0]
    padded = np.concatenate([[True], bright, [True]])
    changes = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(changes == -1)
    ends = np.flatnonzero(changes == 1)
    runs = [(s, e) for s, e in zip(starts, ends) if s > 0 and e < row.size and e - s >= 2]
    if not runs:
        return np.array([], dtype=float)
    widths = np.array([e - s for s, e in runs])
    typical = float(np.percentile(widths, 75))
    centers = [(s + e - 1) / 2 for (s, e), width in zip(runs, widths) if width >= 0.5 * typical]
    return np.array(centers, dtype=float)


def _fit_lattice(centers: np.ndarray) -> tuple[float, float, int] | None:
    if centers.size < MIN_BLACK_KEYS:
        return None
    octaves = centers[5:] - centers[:-5]
    width = float(np.median(octaves)) / 7
    if width <= 0:
        return None

    best: tuple[int, float] | None = None
    for anchor in centers:
        for offset in BLACK_OFFSETS.values():
            origin = anchor - offset * width
            relative = (centers - origin) / width
            octave_position = np.mod(np.round(relative), 7)
            close = np.abs(relative - np.round(relative)) < 0.25
            valid = np.isin(octave_position, list(BLACK_OFFSETS.values()))
            score = int(np.count_nonzero(close & valid))
            if best is None or score > best[0]:
                best = (score, origin)
    if best is None or best[0] < 0.8 * centers.size:
        return None

    origin = best[1]
    indices = np.round((centers - origin) / width)
    matched = np.abs((centers - origin) / width - indices) < 0.25
    slope, intercept = np.polyfit(indices[matched], centers[matched], 1)
    return float(intercept), float(slope), int(np.count_nonzero(matched))


def _snap(x: float, centers: np.ndarray, width: float) -> float:
    nearest = centers[np.argmin(np.abs(centers - x))] if centers.size else x
    return float(nearest) if abs(nearest - x) <= 0.35 * width else x


def _relative_white_pitch(index: int) -> int:
    octave, step = divmod(index, 7)
    return 12 * octave + WHITE_STEPS[step]


def detect_keyboard(frame: np.ndarray, region: tuple[int, int, int, int] | None = None) -> Keyboard | None:
    gray = to_gray(frame)
    x0, y0, x1, y1 = region or (0, 0, gray.shape[1], gray.shape[0])
    area = gray[y0:y1, x0:x1]
    band = find_band(area, 0 if region else area.shape[0] // 3)
    if band is None:
        return None

    centers = _dark_run_centers(area[band.black_row]) + x0
    lattice = _fit_lattice(centers)
    if lattice is None:
        return None
    origin, width, _ = lattice

    bright_columns = np.flatnonzero(area[band.white_row] > band.threshold)
    if bright_columns.size == 0:
        return None
    left = int(bright_columns[0]) + x0
    right = int(bright_columns[-1]) + x0
    first = int(round((left - origin) / width))
    last = int(round((right + 1 - origin) / width)) - 1
    count = last - first + 1
    if count < 7:
        return None

    lowest_relative = _relative_white_pitch(first)
    known = KNOWN_LOWEST_PITCH.get(count)
    if known is not None and (known - lowest_relative) % 12 == 0:
        c_pitch = known - lowest_relative
    else:
        center_relative = (lowest_relative + _relative_white_pitch(last)) / 2
        c_pitch = 12 * round((62 - center_relative) / 12)

    keys: list[Key] = []
    for index in range(first, last + 1):
        pitch = c_pitch + _relative_white_pitch(index)
        keys.append(Key(pitch=pitch, x=origin + (index + 0.5) * width, black=False))
        if index < last and (pitch + 1) % 12 in BLACK_PITCH_CLASSES:
            keys.append(Key(pitch=pitch + 1, x=_snap(origin + (index + 1) * width, centers, width), black=True))

    keys.sort(key=lambda k: k.pitch)
    if keys[0].pitch < 0 or keys[-1].pitch > 127:
        return None
    return Keyboard(
        top=band.top + y0,
        bottom=band.bottom + y0,
        left=left,
        right=right,
        black_row=band.black_row + y0,
        white_row=band.white_row + y0,
        white_width=width,
        keys=tuple(keys),
    )
