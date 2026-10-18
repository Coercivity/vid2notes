import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np
from music21 import chord, clef, key, metadata, meter, note, pitch, stream, tempo

from app.rhythm import Timeline, estimate_timeline, roll_chords
from app.synthesia import Note

METERS = (4, 3, 2)
BASS_PITCH = 55
KEY_TIE = 0.05
LEGATO_BEATS_PERFORMED = 2


@dataclass(frozen=True)
class Meter:
    beats: int
    downbeat: int

    @property
    def name(self) -> str:
        return f"{self.beats}/4"


@dataclass(frozen=True)
class Notation:
    score: stream.Score
    grid: Timeline
    meter: Meter
    key_name: str
    start_seconds: float


@dataclass(frozen=True)
class _Event:
    step: int
    length: int
    pitches: tuple[int, ...]


def _onset_weights(notes: list[Note], grid: Timeline) -> dict[int, float]:
    groups: dict[int, list[Note]] = defaultdict(list)
    for n in notes:
        groups[grid.index(n.start)].append(n)
    beat = 60.0 / grid.bpm
    weights: dict[int, float] = {}
    for step, group in groups.items():
        lowest = min(group, key=lambda n: n.pitch)
        bass = lowest.hand == "left" and lowest.pitch <= BASS_PITCH
        longest = max(n.end - n.start for n in group) / beat
        weights[step] = 0.5 * len(group) + (2.0 if bass else 0.0) + 0.5 * min(longest, 2.0)
    return weights


def estimate_meter(notes: list[Note], grid: Timeline, beats: int | None = None) -> Meter:
    weights = _onset_weights(notes, grid)
    d = grid.division
    phase = max(range(d), key=lambda p: sum(w for k, w in weights.items() if (k - p) % d == 0))
    beat_weights = {(k - phase) // d: w for k, w in weights.items() if (k - phase) % d == 0}
    total = sum(beat_weights.values()) or 1.0

    best: tuple[float, int, int] | None = None
    for m in ([beats] if beats else METERS):
        for offset in range(m):
            share = sum(w for b, w in beat_weights.items() if (b - offset) % m == 0) / total
            score = share * m * (1.0 if m != 2 else 0.9)
            if best is None or score > best[0] + 1e-9:
                best = (score, m, offset)
    assert best is not None
    _, m, offset = best
    return Meter(beats=m, downbeat=phase + offset * d)


def _events(notes: list[Note], grid: Timeline) -> list[_Event]:
    groups: dict[int, list[Note]] = defaultdict(list)
    for n in notes:
        groups[grid.index(n.start)].append(n)
    starts = sorted(groups)
    events: list[_Event] = []
    d = grid.division
    for i, start in enumerate(starts):
        group = groups[start]
        lengths = [max(1, grid.index(n.end) - start) for n in group]
        length = Counter(lengths).most_common(1)[0][0]
        following = starts[i + 1] if i + 1 < len(starts) else None
        if following is not None and following - (start + length) <= d * (LEGATO_BEATS_PERFORMED if grid.performed else 1):
            length = following - start
        elif length >= d and d % 2 == 0:
            half = d // 2
            length = max(half, round(length / half) * half)
        if following is not None:
            length = min(length, following - start)
        events.append(_Event(step=start, length=max(1, length), pitches=tuple(sorted({n.pitch for n in group}))))
    return events


def _spelling_table(k: key.Key) -> dict[int, pitch.Pitch]:
    pitches = list(k.getScale().getPitches())
    if k.mode == "minor":
        pitches += [k.tonic.transpose("M6"), k.tonic.transpose("M7")]
    table: dict[int, pitch.Pitch] = {}
    for p in pitches:
        table.setdefault(p.pitchClass, p)
    return table


def _spell(midi: int, scale: dict[int, pitch.Pitch], prefer_flats: bool) -> pitch.Pitch:
    known = scale.get(midi % 12)
    if known is not None:
        p = pitch.Pitch(known.name, octave=4)
        p.octave += (midi - p.midi) // 12
        return p
    p = pitch.Pitch(midi=midi)
    if prefer_flats and p.accidental is not None and p.accidental.name == "sharp":
        p = p.getEnharmonic()
    elif not prefer_flats and p.accidental is not None and p.accidental.name == "flat":
        p = p.getEnharmonic()
    return p


def _estimate_key(notes: list[Note]) -> key.Key:
    probe = stream.Stream()
    for n in notes:
        element = note.Note(midi=n.pitch)
        element.quarterLength = max(0.25, min(n.end - n.start, 4.0))
        probe.append(element)
    best = probe.analyze("key")
    final_end = max(n.end for n in notes)
    closing = [n for n in notes if final_end - n.end < 1.0]
    if not closing:
        return best
    tonic_hint = min(closing, key=lambda n: n.pitch).pitch % 12
    contenders = [best] + [
        k for k in best.alternateInterpretations if k.correlationCoefficient >= best.correlationCoefficient - KEY_TIE
    ]
    return next((k for k in contenders if k.tonic.pitchClass == tonic_hint), best)


def build_notation(
    notes: list[Note],
    title: str | None = None,
    bpm: float | None = None,
    beats: int | None = None,
) -> Notation:
    notes = roll_chords(notes)
    grid = estimate_timeline(notes, bpm)
    time = estimate_meter(notes, grid, beats)
    detected_key = _estimate_key(notes)
    scale = _spelling_table(detected_key)
    prefer_flats = detected_key.sharps < 0

    d = grid.division
    bar = time.beats * d
    first_step = min(grid.index(n.start) for n in notes)
    start = time.downbeat + math.floor((first_step - time.downbeat) / bar) * bar
    last_step = max(grid.index(n.end) for n in notes)
    total = Fraction(math.ceil((last_step - start) / bar) * bar, d)

    score = stream.Score()
    score.insert(0, metadata.Metadata(title=title or "Transcription"))
    for hand, default_clef in (("right", clef.TrebleClef()), ("left", clef.BassClef())):
        part = stream.Part()
        part.partName = "Right hand" if hand == "right" else "Left hand"
        hand_notes = [n for n in notes if n.hand == hand]
        events = _events(hand_notes, grid)

        body = stream.Part()
        for event in events:
            offset = Fraction(event.step - start, d)
            length = Fraction(event.length, d)
            spelled = [_spell(m, scale, prefer_flats) for m in event.pitches]
            element = note.Note(spelled[0]) if len(spelled) == 1 else chord.Chord(spelled)
            element.duration.quarterLength = length
            body.insert(offset, element)

        chosen_clef = clef.bestClef(body, recurse=True) if events else default_clef
        if hand == "left" and not isinstance(chosen_clef, (clef.BassClef, clef.TrebleClef)):
            chosen_clef = default_clef
        part.insert(0, chosen_clef)
        part.insert(0, key.KeySignature(detected_key.sharps))
        part.insert(0, meter.TimeSignature(time.name))
        if hand == "right":
            part.insert(0, tempo.MetronomeMark(number=round(grid.bpm)))
        for element in body.notes:
            part.insert(element.offset, element)
        part.makeRests(refStreamOrTimeRange=[0, total], fillGaps=True, inPlace=True)
        score.insert(0, part)

    score = score.makeNotation()
    return Notation(
        score=score,
        grid=grid,
        meter=time,
        key_name=detected_key.name.replace("-", "b"),
        start_seconds=grid.seconds(start),
    )


def write_musicxml(notation: Notation, path: Path) -> None:
    notation.score.write("musicxml", fp=str(path))
