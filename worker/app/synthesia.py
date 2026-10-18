from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.imaging import crop_pixels
from app.keyboard import Keyboard, detect_keyboard
from app.messages import Crop
from app.video import PermanentError, probe, sample_frames

PROBE_FRAMES = 40
ACTIVE_THRESHOLD = 45.0
MIN_HUE_GAP = 20
SCAN_OFFSETS = (1, 5, 9, 13, 17)
EDGE_SEARCH = 120
EDGE_QUIET = 0.1
EDGE_MARGIN = 2
EDGE_MIN_GAP = 3
ATTACHED_SEARCH = 15
DECORATION_VALUE = 60
DECORATION_SHARE = 0.5
SPLIT_CLUSTER = 3
SPLIT_MARGIN = 2.5
NOTE_SATURATION = 50
BAR_VALUE = 110
BARS_MAJORITY = 3
BAR_OFFSETS = (5, 9, 13)
MIN_BAR_WIDTH = 0.2
MERGED_BAR_WIDTH = 1.3
CORE_SHARE = 0.85
PLATEAU_DEPTH = 2
PLATEAU_SHARE = 0.5
SHADOW_FRAMES = 3.5
SHADOW_DISTANCE = 2
TWIN_FRAMES = 1.5
BACKGROUND_PERCENTILE = 10
MIN_LANE_RUNS = 20
LANE_SCALE = 0.04
LANE_SCALE_STEP = 0.0025
LANE_SHIFT = 0.6
LANE_SHIFT_STEP = 0.02
LANE_TOLERANCE = 0.15
MAX_FIT_RUNS = 4000
LANE_VIABLE = 0.97
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
FIT_MIN_WIDTH = 0.45
LANE_MAX_MOVE = 0.2
CLASS_MARGIN = 0.1
LANE_REFINEMENTS = 2
LANE_ASSIGN = 0.3
MIN_LANE_SAMPLES = 5
MIN_NOTE_SECONDS = 0.035
NOTE_HUE_TOLERANCE = 20
KEY_AGREEMENT = 0.5
AGREEMENT_FRAMES = 4
BLACK_BAR_SPREAD = 0.15
WHITE_BAR_SPREAD = 0.2


class KeyboardNotFoundError(PermanentError):
    pass


@dataclass(frozen=True)
class Note:
    pitch: int
    start: float
    end: float
    hand: str


@dataclass(frozen=True)
class Transcription:
    notes: list[Note]
    keyboard: Keyboard
    source: str


def _falling_edge(strips: list[np.ndarray], bottom: int) -> int:
    stack = np.stack(strips)
    median = np.median(stack.astype(np.float32), axis=0)
    moving = np.linalg.norm(stack.astype(np.float32) - median, axis=3) > ACTIVE_THRESHOLD
    saturation = cv2.cvtColor(stack.reshape(-1, stack.shape[2], 3), cv2.COLOR_BGR2HSV)[:, :, 1]
    colored = saturation.reshape(stack.shape[:3]) >= NOTE_SATURATION
    bars = (moving & colored).mean(axis=(0, 2))
    median_hsv = cv2.cvtColor(np.clip(median, 0, 255).astype(np.uint8), cv2.COLOR_BGR2HSV)
    decoration = ((median_hsv[:, :, 1] >= NOTE_SATURATION) & (median_hsv[:, :, 2] >= DECORATION_VALUE)).mean(axis=1)
    decorative = decoration > DECORATION_SHARE
    quiet = bars < EDGE_QUIET * max(bars.max(), 1e-9)

    row = len(bars) - 1
    while row >= 0 and decorative[row]:
        row -= 1
    gap = _quiet_band_above(quiet, row)
    if gap is not None:
        row = gap
    while row >= 0 and (quiet[row] or decorative[row]):
        row -= 1
    if row < 0:
        return bottom
    return bottom - (len(bars) - 1 - row) - EDGE_MARGIN


def _quiet_band_above(quiet: np.ndarray, row: int) -> int | None:
    for candidate in range(row, max(row - ATTACHED_SEARCH, -1), -1):
        if candidate - EDGE_MIN_GAP + 1 >= 0 and quiet[candidate - EDGE_MIN_GAP + 1 : candidate + 1].all():
            return candidate
    return None


@dataclass(frozen=True)
class Stage:
    keyboard: Keyboard
    edge: int
    background: np.ndarray | None
    background_top: int
    lanes: np.ndarray


def find_keyboard(path: Path, crop: Crop, start: float, end: float) -> Stage:
    info = probe(path)
    step = max((end - start) / PROBE_FRAMES, 1 / info.fps)
    candidates: list[tuple[Keyboard, np.ndarray]] = []
    for _, frame in sample_frames(path, step, start, end):
        h, w = frame.shape[:2]
        keyboard = detect_keyboard(frame, crop_pixels(crop, w, h))
        if keyboard is not None:
            strip = frame[max(0, keyboard.top - EDGE_SEARCH) : keyboard.top]
            candidates.append((keyboard, strip))
    if not candidates:
        raise KeyboardNotFoundError("Piano keyboard not found in the selected region")
    tops = [round(k.top / 4) for k, _ in candidates]
    top = max(set(tops), key=tops.count)
    placed = [(k, strip) for (k, strip), t in zip(candidates, tops) if t == top]
    signatures = [(k.lowest, k.highest) for k, _ in placed]
    best = max(set(signatures), key=signatures.count)
    keyboard = next(k for (k, _), sig in zip(placed, signatures) if sig == best)
    strips = [strip for _, strip in placed if strip.shape == placed[0][1].shape]
    xs = np.array([k.x for k in keyboard.keys])
    if not strips or strips[0].shape[0] == 0:
        return Stage(keyboard=keyboard, edge=keyboard.top - 1, background=None, background_top=0, lanes=xs)
    background = np.percentile(np.stack(strips).astype(np.float32), BACKGROUND_PERCENTILE, axis=0)
    edge = _falling_edge([strip[:, keyboard.left : keyboard.right + 1] for strip in strips], keyboard.top - 1)
    background_top = keyboard.top - strips[0].shape[0]
    return Stage(keyboard=keyboard, edge=edge, background=background, background_top=background_top, lanes=xs)


def _class_distance(centers: np.ndarray, lanes: np.ndarray) -> np.ndarray:
    order = np.sort(lanes)
    index = np.clip(np.searchsorted(order, centers), 1, len(order) - 1)
    return np.minimum(np.abs(centers - order[index - 1]), np.abs(centers - order[index]))


def _tonality(pitches: np.ndarray) -> float:
    histogram = np.bincount(pitches % 12, minlength=12).astype(float)
    if histogram.sum() == 0:
        return 0.0
    return max(
        float(np.corrcoef(histogram, np.roll(profile, tonic))[0, 1])
        for tonic in range(12)
        for profile in (MAJOR_PROFILE, MINOR_PROFILE)
    )


def fit_lanes(runs: np.ndarray, keyboard: Keyboard) -> tuple[np.ndarray, float | None]:
    xs = np.array([k.x for k in keyboard.keys])
    black = np.array([k.black for k in keyboard.keys])
    pitches = np.array([k.pitch for k in keyboard.keys])
    width = keyboard.white_width
    runs = runs[runs[:, 1] >= FIT_MIN_WIDTH * width] if len(runs) else runs
    if len(runs) < MIN_LANE_RUNS:
        return xs, None
    if len(runs) > MAX_FIT_RUNS:
        runs = runs[np.random.default_rng(0).choice(len(runs), MAX_FIT_RUNS, replace=False)]
    widths = runs[:, 1]
    low, high = np.percentile(widths, 20), np.percentile(widths, 80)
    split = (low + high) / 2 if high > 1.3 * low else None
    groups = [(runs[:, 0], np.ones(len(xs), dtype=bool))] if split is None else [
        (runs[widths < split, 0], black),
        (runs[widths >= split, 0], ~black),
    ]
    center = (keyboard.left + keyboard.right) / 2

    candidates: list[tuple[int, float, float]] = []
    for scale in np.arange(1 - LANE_SCALE, 1 + LANE_SCALE + 1e-9, LANE_SCALE_STEP):
        for shift in np.arange(-LANE_SHIFT, LANE_SHIFT + 1e-9, LANE_SHIFT_STEP) * width:
            moved = center + scale * (xs - center) + shift
            score = 0
            for centers, members in groups:
                if len(centers) and members.any():
                    score += int(np.count_nonzero(_class_distance(centers, moved[members]) < LANE_TOLERANCE * width))
            candidates.append((score, scale, shift))
    top = max(c[0] for c in candidates)
    viable = [c for c in candidates if c[0] >= LANE_VIABLE * top]

    def tonal(candidate: tuple[int, float, float]) -> float:
        _, scale, shift = candidate
        moved = center + scale * (xs - center) + shift
        chosen = np.array([_nearest_lane(x, w, moved, black, split, width) for x, w in runs])
        return _tonality(pitches[chosen])

    _, scale, shift = max(viable, key=lambda c: (round(tonal(c), 2), c[0]))
    fitted = center + scale * (xs - center) + shift
    classes = np.array([k.pitch % 12 if k.black else -1 for k in keyboard.keys])
    lanes = fitted.copy()
    for _ in range(LANE_REFINEMENTS):
        nearest = np.array([_nearest_lane(x, w, lanes, black, split, width) for x, w in runs])
        residual = runs[:, 0] - fitted[nearest]
        close = np.abs(runs[:, 0] - lanes[nearest]) < LANE_ASSIGN * width
        offsets = np.zeros(len(lanes))
        for pitch_class in np.unique(classes):
            members = classes == pitch_class
            assigned = residual[close & members[nearest]]
            if assigned.size >= MIN_LANE_SAMPLES:
                offsets[members] = np.clip(np.median(assigned), -LANE_MAX_MOVE * width, LANE_MAX_MOVE * width)
        lanes = fitted + offsets
    return lanes, split


def _nearest_lane(center: float, span: float, lanes: np.ndarray, black: np.ndarray, split: float | None, width: float) -> int:
    distance = np.abs(lanes - center)
    if split is not None and abs(span - split) > CLASS_MARGIN * width:
        distance = np.where(black == (span < split), distance, np.inf)
    return int(np.argmin(distance))


def _patch(xs: np.ndarray, half: int, row: np.ndarray | int, width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    offsets = np.arange(-half, half + 1)
    x = np.clip(np.round(xs[:, None] + offsets[None, :]).astype(int), 0, width - 1)
    y = np.clip(np.broadcast_to(np.asarray(row).reshape(-1, 1), x.shape), 0, height - 1)
    return y, x


class _Sampler:
    def __init__(self, stage: Stage, frame_height: int, frame_width: int):
        keyboard, edge = stage.keyboard, stage.edge
        xs = np.array([k.x for k in keyboard.keys])
        key_rows = np.array([keyboard.black_row if k.black else keyboard.white_row for k in keyboard.keys])
        self.black = np.array([k.black for k in keyboard.keys])
        lanes = stage.lanes
        self.xs = lanes
        self.width = keyboard.white_width
        self._key = _patch(xs, max(1, int(keyboard.white_width * 0.15)), key_rows, frame_width, frame_height)
        self.offsets = [offset for offset in SCAN_OFFSETS if edge - offset >= 0]
        rows = [edge - offset for offset in self.offsets]
        self.has_scan = bool(rows)
        rows = rows or [0]
        spread = keyboard.white_width * np.where(self.black, BLACK_BAR_SPREAD, WHITE_BAR_SPREAD)
        scan_x = np.clip(
            np.round(np.stack([lanes - spread, lanes, lanes + spread], axis=1)).astype(int), 0, frame_width - 1
        )
        self._scan = (
            np.broadcast_to(np.array(rows)[:, None, None], (len(rows), *scan_x.shape)),
            np.broadcast_to(scan_x[None, :, :], (len(rows), *scan_x.shape)),
        )
        self._bar_rows: list[int] = []
        self._background: np.ndarray | None = None
        if stage.background is not None:
            bar_rows = [edge - offset for offset in BAR_OFFSETS if 0 <= edge - offset - stage.background_top]
            bar_rows = [row for row in bar_rows if row - stage.background_top < stage.background.shape[0]]
            if bar_rows:
                self._bar_rows = bar_rows
                self._background = stage.background[[row - stage.background_top for row in bar_rows]]
        self.bar_rows = max(1, len(self._bar_rows))

    def sample(self, frame: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
        keys = frame[self._key].mean(axis=1).astype(np.float32)
        scan = frame[self._scan].astype(np.float32)
        cores: list[np.ndarray] = []
        if self._background is not None:
            pixels = frame[self._bar_rows]
            hsv = cv2.cvtColor(pixels, cv2.COLOR_BGR2HSV)
            changed = np.linalg.norm(pixels.astype(np.float32) - self._background, axis=2) > ACTIVE_THRESHOLD
            colored = (hsv[:, :, 1] >= NOTE_SATURATION) & (hsv[:, :, 2] >= BAR_VALUE)
            for r, active in enumerate(changed & colored):
                found = [
                    ((a + b - 1) / 2, b - a, float(np.median(hsv[r, a:b, 0])))
                    for a, b in _bar_cores(active, hsv[r, :, 2])
                    if b - a >= MIN_BAR_WIDTH * self.width
                ]
                cores.append(np.array(found, dtype=np.float32).reshape(-1, 3))
        return keys, scan, cores


def _spans(mask: np.ndarray) -> list[tuple[int, int]]:
    padded = np.concatenate([[False], mask, [False]])
    changes = np.diff(padded.astype(np.int8))
    return list(zip(np.flatnonzero(changes == 1).tolist(), np.flatnonzero(changes == -1).tolist()))


def _bar_cores(active: np.ndarray, value: np.ndarray) -> list[tuple[int, int]]:
    cores: list[tuple[int, int]] = []
    for start, end in _spans(active):
        cores.extend(_plateaus(value[start:end].astype(np.float32), start, 0))
    return sorted(cores)


def _plateaus(brightness: np.ndarray, offset: int, depth: int) -> list[tuple[int, int]]:
    if brightness.size == 0:
        return []
    core = brightness >= CORE_SHARE * brightness.max()
    found = [(offset + a, offset + b) for a, b in _spans(core)]
    if depth >= PLATEAU_DEPTH:
        return found
    for a, b in _spans(~core):
        inner = _plateaus(brightness[a:b], offset + a, depth + 1)
        if sum(e - s for s, e in inner) >= PLATEAU_SHARE * (b - a):
            found.extend(inner)
    return found


def _assign_bars(
    cores: list[list[np.ndarray]], lanes: np.ndarray, black: np.ndarray, width: float, split: float | None
) -> tuple[np.ndarray, np.ndarray]:
    frames = len(cores)
    rows = max((len(c) for c in cores), default=0) or 1
    active = np.zeros((frames, rows, len(lanes)), dtype=bool)
    hue = np.full((frames, len(lanes)), -1.0)
    for t, frame_cores in enumerate(cores):
        for r, found in enumerate(frame_cores):
            for center, span, value in found:
                if span <= MERGED_BAR_WIDTH * width:
                    targets = [_nearest_lane(center, span, lanes, black, split, width)]
                else:
                    margin = 0.25 * width
                    left, right = center - span / 2, center + span / 2
                    targets = np.flatnonzero(~black & (lanes - margin >= left) & (lanes + margin <= right)).tolist()
                for index in targets:
                    active[t, r, index] = True
                    hue[t, index] = value
    return active, hue


def _to_hsv(colors: np.ndarray) -> np.ndarray:
    pixels = np.clip(colors, 0, 255).astype(np.uint8).reshape(-1, 1, 3)
    return cv2.cvtColor(pixels, cv2.COLOR_BGR2HSV).reshape(*colors.shape[:-1], 3).astype(float)


def _rest_colors(samples: np.ndarray, black: np.ndarray) -> np.ndarray:
    rest = np.median(samples, axis=0)
    saturated = _to_hsv(rest)[:, 1] >= NOTE_SATURATION
    for group in (black, ~black):
        if not group.any():
            continue
        typical = np.median(rest[group], axis=0)
        drifted = group & saturated & (np.linalg.norm(rest - typical, axis=1) > ACTIVE_THRESHOLD)
        rest[drifted] = typical
    return rest


def _hue_distance(a: np.ndarray | float, b: float) -> np.ndarray:
    difference = np.abs(np.asarray(a) - b) % 180
    return np.minimum(difference, 180 - difference)


def _runs(active: np.ndarray) -> list[tuple[int, int]]:
    padded = np.concatenate([[False], active, [False]])
    changes = np.diff(padded.astype(np.int8))
    return list(zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)))


def _rising(active: np.ndarray) -> np.ndarray:
    return np.flatnonzero(active[1:] & ~active[:-1]) + 1


def _pixels_per_frame(key_active: np.ndarray, row_active: np.ndarray, offsets: np.ndarray) -> float | None:
    if offsets.size < 2:
        return None
    lags: list[int] = []
    for index in range(key_active.shape[1]):
        top_edges = _rising(row_active[:, -1, index])
        low_edges = _rising(row_active[:, 0, index])
        for onset in _rising(key_active[:, index]):
            low = low_edges[(low_edges <= onset + 1) & (low_edges >= onset - 15)]
            top = top_edges[(top_edges <= onset + 1) & (top_edges >= onset - 30)]
            if low.size and top.size:
                lags.append(int(low[-1] - top[-1]))
    lags = [lag for lag in lags if lag >= 0]
    if len(lags) < 3:
        return None
    lag = float(np.median(lags))
    return float(offsets[-1] - offsets[0]) / lag if lag > 0 else float("inf")


def _bar_splits(rows: np.ndarray, start: int, end: int) -> list[int]:
    window = rows[start:end]
    rising = np.flatnonzero((window[1:] & ~window[:-1]).any(axis=1)) + start + 1
    splits: list[int] = []
    for frame in rising.tolist():
        if not start + SPLIT_MARGIN <= frame <= end - SPLIT_MARGIN:
            continue
        if splits and frame - splits[-1] <= SPLIT_CLUSTER:
            continue
        splits.append(frame)
    return splits


def _key_agreement(key_active: np.ndarray, row_active: np.ndarray) -> float:
    if not row_active.any():
        return 1.0
    arrivals = row_active.any(axis=1)
    matched = 0
    total = 0
    for index in range(key_active.shape[1]):
        onsets = _rising(key_active[:, index])
        total += onsets.size
        for onset in onsets:
            window = arrivals[max(0, onset - AGREEMENT_FRAMES) : onset + AGREEMENT_FRAMES + 1, index]
            matched += bool(window.any())
    return matched / total if total else 0.0


def _splits(
    rows: np.ndarray,
    row_hsv: np.ndarray,
    key_hsv: np.ndarray,
    offsets: np.ndarray,
    speed: float | None,
    start: int,
    end: int,
) -> list[int]:
    lit = key_hsv[start:end]
    lit = lit[lit[:, 1] >= NOTE_SATURATION]
    note_hue = float(np.median(lit[:, 0])) if lit.size else None
    usable = range(rows.shape[1]) if speed else range(1)
    projected: list[float] = []
    for r in usable:
        lead = offsets[r] / speed if speed else 0.0
        for frame in _rising(rows[:, r]):
            body = row_hsv[min(frame + 1, len(row_hsv) - 1), r]
            if body[1] < NOTE_SATURATION:
                continue
            if note_hue is not None and _hue_distance(body[0], note_hue) > NOTE_HUE_TOLERANCE:
                continue
            projected.append(frame + lead)
    inside = sorted(p for p in projected if start + SPLIT_MARGIN <= p <= end - SPLIT_MARGIN)
    splits: list[float] = []
    for value in inside:
        if splits and value - splits[-1] <= SPLIT_CLUSTER:
            continue
        splits.append(value)
    return [int(round(s)) for s in splits]


def _assign_hands(pitches: list[int], hues: list[float]) -> list[str]:
    if not pitches:
        return []
    known = [h for h in hues if h >= 0]
    ordered = sorted(set(round(h) for h in known))
    gaps = []
    for i, hue in enumerate(ordered):
        following = ordered[(i + 1) % len(ordered)]
        gap = (following - hue) % 180
        if gap >= MIN_HUE_GAP:
            gaps.append((hue, following))
    if len(gaps) == 2:
        boundaries = sorted(b for _, b in gaps)

        def cluster(hue: float) -> int:
            h = round(hue)
            return 0 if boundaries[0] <= h < boundaries[1] else 1

        labels = [cluster(h) if h >= 0 else -1 for h in hues]
        means = [np.mean([p for p, l in zip(pitches, labels) if l == c] or [0]) for c in (0, 1)]
        right = int(np.argmax(means))
        return [
            ("right" if label == right else "left") if label >= 0 else ("right" if pitch >= 60 else "left")
            for pitch, label in zip(pitches, labels)
        ]
    return ["right" if pitch >= 60 else "left" for pitch in pitches]


def transcribe(
    path: Path,
    crop: Crop,
    start: float,
    end: float,
    on_progress: Callable[[float], None],
) -> Transcription:
    stage = find_keyboard(path, crop, start, end)
    keyboard = stage.keyboard
    info = probe(path)
    sampler = _Sampler(stage, info.height, info.width)

    key_samples: list[np.ndarray] = []
    scan_samples: list[np.ndarray] = []
    bar_samples: list[list[np.ndarray]] = []
    first_frame: int | None = None
    for time, frame in sample_frames(path, 0, start, end):
        if first_frame is None:
            first_frame = round(time * info.fps)
        keys, scan, cores = sampler.sample(frame)
        key_samples.append(keys)
        scan_samples.append(scan)
        bar_samples.append(cores)
        on_progress(min(max((time - start) / max(end - start, 0.001), 0.0), 1.0))

    if not key_samples:
        raise PermanentError("No frames in the selected time range")

    keys = np.stack(key_samples)
    scan = np.stack(scan_samples)
    key_active = np.linalg.norm(keys - _rest_colors(keys, sampler.black), axis=2) > ACTIVE_THRESHOLD
    frames, rows, count = scan.shape[:3]
    scan_points = np.zeros((frames, rows, count, 3), dtype=bool)
    for r in range(rows):
        flat = scan[:, r].reshape(frames, count * 3, 3)
        rest = _rest_colors(flat, np.zeros(count * 3, dtype=bool))
        changed = np.linalg.norm(flat - rest, axis=2) > ACTIVE_THRESHOLD
        hsv = _to_hsv(flat)
        colored = (hsv[:, :, 1] >= NOTE_SATURATION) & (hsv[:, :, 2] >= BAR_VALUE)
        scan_points[:, r] = (changed & colored).reshape(frames, count, 3)
    row_active = scan_points.all(axis=3)
    if not sampler.has_scan:
        row_active[:] = False
    row_hsv = _to_hsv(scan[:, :, :, 1])
    key_hsv = _to_hsv(keys)
    offsets = np.array(sampler.offsets, dtype=float)
    speed = _pixels_per_frame(key_active, row_active, offsets)
    use_scan = _key_agreement(key_active, row_active) < KEY_AGREEMENT
    if use_scan:
        found = [core[:, :2] for frame_cores in bar_samples for core in frame_cores if len(core)]
        runs = np.concatenate(found) if found else np.zeros((0, 2))
        lanes, split = fit_lanes(runs.astype(float), keyboard)
        bar_active, bar_hue = _assign_bars(bar_samples, lanes, sampler.black, keyboard.white_width, split)
    else:
        bar_active = np.zeros((frames, 1, count), dtype=bool)
        bar_hue = np.full((frames, count), -1.0)
    scan_active = bar_active.sum(axis=1) >= (bar_active.shape[1] // 2 + 1)
    source = "bars" if use_scan else "keys"
    offset = (first_frame or 0) / info.fps

    pitches: list[int] = []
    spans: list[tuple[float, float]] = []
    hues: list[float] = []
    supports: list[float] = []
    for index, key in enumerate(keyboard.keys):
        primary = scan_active[:, index] if use_scan else key_active[:, index]
        for a, b in _runs(primary):
            if use_scan:
                splits = _bar_splits(bar_active[:, :, index], a, b)
            else:
                splits = _splits(
                    row_active[:, :, index], row_hsv[:, :, index], key_hsv[:, index], offsets, speed, a, b
                )
            cuts = [a, *splits, b]
            for s, e in zip(cuts, cuts[1:]):
                if e <= s:
                    continue
                if (e - s) / info.fps < MIN_NOTE_SECONDS:
                    continue
                if use_scan:
                    seen = bar_hue[s:e, index]
                    lit = np.stack([seen[seen >= 0], np.full(np.count_nonzero(seen >= 0), 255.0)], axis=1)
                else:
                    source_hsv = key_hsv[s:e, index]
                    lit = source_hsv[source_hsv[:, 1] >= NOTE_SATURATION]
                pitches.append(key.pitch)
                spans.append((offset + s / info.fps, offset + e / info.fps))
                hues.append(float(np.median(lit[:, 0])) if lit.size else -1.0)
                supports.append(float(bar_active[s:e, :, index].mean() if use_scan else key_active[s:e, index].mean()))

    hands = _assign_hands(pitches, hues)
    notes = [Note(pitch=p, start=s, end=e, hand=h) for p, (s, e), h in zip(pitches, spans, hands)]
    notes = _drop_twins(notes, supports, TWIN_FRAMES / info.fps)
    notes = _drop_shadows(notes, SHADOW_FRAMES / info.fps)
    notes.sort(key=lambda n: (n.start, n.pitch))
    return Transcription(notes=notes, keyboard=keyboard, source=source)


def _drop_twins(notes: list[Note], supports: list[float], tolerance: float) -> list[Note]:
    order = sorted(range(len(notes)), key=lambda i: notes[i].start)
    dropped: set[int] = set()
    for position, i in enumerate(order):
        a = notes[i]
        for j in order[position + 1 :]:
            b = notes[j]
            if b.start - a.start > tolerance:
                break
            if abs(a.pitch - b.pitch) == 1 and abs(a.end - b.end) <= 2 * tolerance:
                dropped.add(i if supports[i] < supports[j] else j)
    return [note for k, note in enumerate(notes) if k not in dropped]


def _drop_shadows(notes: list[Note], longest: float) -> list[Note]:
    kept: list[Note] = []
    for note in notes:
        length = note.end - note.start
        if length <= longest and any(
            other is not note
            and 0 < abs(other.pitch - note.pitch) <= SHADOW_DISTANCE
            and other.end - other.start > length
            and other.start < note.end
            and note.start < other.end
            for other in notes
        ):
            continue
        kept.append(note)
    return kept
