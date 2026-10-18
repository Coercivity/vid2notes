import math
from dataclasses import dataclass

import numpy as np

from app.synthesia import Note

MIN_BPM = 40.0
MAX_BPM = 220.0
BPM_STEP = 0.1
PREFERRED_BPM = 110.0
DIVISIONS = (4, 3)
PERFORMED_DIVISIONS = (2, 3)
TRIPLET_PREFERENCE = 0.7
CHORD_WINDOW = 0.03
ROLLED_CHORD_WINDOW = 0.07
CANDIDATE_SHARE = 0.9
TEMPO_PRIOR = 0.15
STEADY_STRENGTH = 0.6
BASS_PITCH = 55

ENVELOPE_RATE = 100
ENVELOPE_SIGMA = 2.0
TRACKING_TIGHTNESS = 100.0
TEMPO_OCTAVE_SPREAD = 0.9
TRACKING_PREFERRED_BPM = 120.0


@dataclass(frozen=True)
class Timeline:
    beats: np.ndarray
    division: int
    performed: bool = False

    @property
    def bpm(self) -> float:
        return 60.0 / float(np.median(np.diff(self.beats)))

    def position(self, seconds: float) -> float:
        beats = self.beats
        i = int(np.clip(np.searchsorted(beats, seconds, side="right") - 1, 0, len(beats) - 2))
        return i + (seconds - beats[i]) / (beats[i + 1] - beats[i])

    def index(self, seconds: float) -> int:
        return round(self.position(seconds) * self.division)

    def seconds(self, step: float) -> float:
        position = step / self.division
        i = int(np.clip(math.floor(position), 0, len(self.beats) - 2))
        return float(self.beats[i] + (position - i) * (self.beats[i + 1] - self.beats[i]))


def _onsets(notes: list[Note], window: float = CHORD_WINDOW) -> np.ndarray:
    times = sorted(n.start for n in notes)
    merged: list[float] = []
    for time in times:
        if not merged or time - merged[-1] > window:
            merged.append(time)
    return np.array(merged)


def _alignment(onsets: np.ndarray, steps: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    phases = np.exp(2j * np.pi * onsets[None, :] / steps[:, None]).mean(axis=1)
    return np.abs(phases), np.angle(phases)


def _on_beat_share(onsets: np.ndarray, beat: float, step: float, origin: float) -> float:
    steps = np.round((onsets - origin) / step).astype(int)
    division = max(1, round(beat / step))
    counts = np.bincount(np.mod(steps, division), minlength=division)
    return float(counts.max() / steps.size)


def _refine(onsets: np.ndarray, step: float, origin: float) -> tuple[float, float]:
    indices = np.round((onsets - origin) / step)
    if np.unique(indices).size < 2:
        return step, origin
    slope, intercept = np.polyfit(indices, onsets, 1)
    return float(slope), float(intercept)


def _uniform(onsets: np.ndarray, bpm: float, division: int, origin: float, end: float) -> Timeline:
    beat = 60.0 / bpm
    first = origin - beat * math.ceil(max(origin - 0.0, 0.0) / beat + 1)
    count = int(math.ceil((end - first) / beat)) + 2
    return Timeline(beats=first + beat * np.arange(count), division=division)


def _steady_grid(onsets: np.ndarray, bpm: float | None) -> tuple[float, float, int, float]:
    candidates = np.array([bpm]) if bpm else np.arange(MIN_BPM, MAX_BPM + BPM_STEP, BPM_STEP)
    options: list[tuple[float, float, int, float]] = []
    for division in DIVISIONS:
        steps = 60.0 / (candidates * division)
        strength, angle = _alignment(onsets, steps)
        if bpm:
            peaks = [0]
        else:
            peaks = [
                i
                for i in range(1, len(strength) - 1)
                if strength[i] >= strength[i - 1] and strength[i] >= strength[i + 1]
            ]
        for i in peaks:
            origin = float(angle[i] / (2 * np.pi) * steps[i])
            options.append((float(strength[i]), float(candidates[i]), division, origin))

    best_strength = max(o[0] for o in options)
    viable = [o for o in options if o[0] >= CANDIDATE_SHARE * best_strength]
    strength, chosen, division, origin = max(
        viable,
        key=lambda o: (
            _on_beat_share(onsets, 60.0 / o[1], 60.0 / (o[1] * o[2]), o[3])
            - TEMPO_PRIOR * abs(math.log2(o[1] / PREFERRED_BPM))
            + (0.01 if o[2] == 4 else 0.0)
        ),
    )
    step = 60.0 / (chosen * division)
    first = float(onsets[0])
    origin = first - ((first - origin) % step)
    if not bpm:
        step, origin = _refine(onsets, step, origin)
        chosen = 60.0 / (step * division)
    return strength, chosen, division, origin


def _envelope(notes: list[Note], length: int) -> np.ndarray:
    envelope = np.zeros(length)
    for n in notes:
        index = int(round(n.start * ENVELOPE_RATE))
        if 0 <= index < length:
            envelope[index] += 1.0 + (2.0 if n.hand == "left" and n.pitch <= BASS_PITCH else 0.0)
    radius = int(4 * ENVELOPE_SIGMA)
    kernel = np.exp(-0.5 * (np.arange(-radius, radius + 1) / ENVELOPE_SIGMA) ** 2)
    return np.convolve(envelope, kernel, mode="same")


def _global_period(envelope: np.ndarray, bpm: float | None) -> float:
    if bpm:
        return 60.0 * ENVELOPE_RATE / bpm
    centered = envelope - envelope.mean()
    lags = np.arange(int(60 * ENVELOPE_RATE / MAX_BPM), int(60 * ENVELOPE_RATE / MIN_BPM) + 1)
    correlation = np.array([np.dot(centered[:-lag], centered[lag:]) for lag in lags])
    tempi = 60.0 * ENVELOPE_RATE / lags
    prior = np.exp(-0.5 * (np.log2(tempi / TRACKING_PREFERRED_BPM) / TEMPO_OCTAVE_SPREAD) ** 2)
    return float(lags[int(np.argmax(np.maximum(correlation, 0) * prior))])


def _track_beats(envelope: np.ndarray, period: float) -> np.ndarray:
    size = len(envelope)
    score = envelope.copy()
    previous = np.full(size, -1)
    low, high = int(round(period / 2)), int(round(2 * period))
    for t in range(low, size):
        start = max(0, t - high)
        end = t - low
        if end < start:
            continue
        candidates = np.arange(start, end + 1)
        penalty = TRACKING_TIGHTNESS * np.log((t - candidates) / period) ** 2
        values = score[candidates] - penalty
        best = int(np.argmax(values))
        if values[best] > 0:
            score[t] = envelope[t] + values[best]
            previous[t] = candidates[best]

    active = np.flatnonzero(envelope > envelope.max() * 0.05)
    tail = slice(max(0, active[-1] - int(period)), min(size, active[-1] + int(period)))
    beat = tail.start + int(np.argmax(score[tail]))
    beats = [beat]
    while previous[beat] >= 0:
        beat = int(previous[beat])
        beats.append(beat)
    return np.array(beats[::-1], dtype=float) / ENVELOPE_RATE


def _extend(beats: np.ndarray, start: float, end: float) -> np.ndarray:
    head = beats[1] - beats[0]
    tail = beats[-1] - beats[-2]
    before = np.arange(beats[0] - head, start - 2 * head, -head)[::-1]
    after = np.arange(beats[-1] + tail, end + 2 * tail, tail)
    return np.concatenate([before, beats, after])


def _choose_division(notes: list[Note], beats: np.ndarray) -> int:
    probe = Timeline(beats=beats, division=1)
    positions = np.array([probe.position(n.start) for n in notes])
    ratios = {d: float(np.mean(np.abs(positions * d - np.round(positions * d)))) / 0.25 for d in PERFORMED_DIVISIONS}
    return 3 if ratios[3] < TRIPLET_PREFERENCE * ratios[2] else 2


def roll_chords(notes: list[Note]) -> list[Note]:
    result: list[Note] = []
    for hand in ("right", "left"):
        group: list[Note] = []
        for n in sorted((n for n in notes if n.hand == hand), key=lambda n: n.start):
            if group and n.start - group[0].start > ROLLED_CHORD_WINDOW:
                result.extend(_align(group))
                group = []
            group.append(n)
        result.extend(_align(group))
    return sorted(result, key=lambda n: (n.start, n.pitch))


def _align(group: list[Note]) -> list[Note]:
    if not group:
        return []
    start = group[0].start
    return [Note(pitch=n.pitch, start=start, end=max(n.end, start + 0.01), hand=n.hand) for n in group]


def estimate_timeline(notes: list[Note], bpm: float | None = None) -> Timeline:
    end = max(n.end for n in notes)
    onsets = _onsets(notes)
    if onsets.size < 4:
        return _uniform(onsets, bpm or 120.0, 4, float(onsets[0]) if onsets.size else 0.0, end)

    strength, chosen, division, origin = _steady_grid(onsets, bpm)
    if strength >= STEADY_STRENGTH:
        return _uniform(onsets, chosen, division, origin, end)

    length = int(math.ceil((end + 2.0) * ENVELOPE_RATE))
    envelope = _envelope(notes, length)
    beats = _track_beats(envelope, _global_period(envelope, bpm))
    if beats.size < 4:
        return _uniform(onsets, chosen, division, origin, end)
    beats = _extend(beats, float(onsets[0]), end)
    return Timeline(beats=beats, division=_choose_division(notes, beats), performed=True)
