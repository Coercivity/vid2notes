from pathlib import Path

import mido

from app.synthesia import Note

TICKS_PER_BEAT = 480
VELOCITY = 80
TRACKS = (("right", "Right hand"), ("left", "Left hand"))


def save_midi(notes: list[Note], path: Path, bpm: float = 120.0, origin: float = 0.0) -> None:
    tempo = mido.bpm2tempo(bpm)

    def ticks(seconds: float) -> int:
        return max(0, round(mido.second2tick(seconds - origin, TICKS_PER_BEAT, tempo)))

    midi = mido.MidiFile(ticks_per_beat=TICKS_PER_BEAT)
    for hand, name in TRACKS:
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=name, time=0))
        if hand == "right":
            track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
        track.append(mido.Message("program_change", program=0, time=0))

        events: list[tuple[int, int, mido.Message]] = []
        for note in notes:
            if note.hand != hand:
                continue
            events.append((ticks(note.start), 1, mido.Message("note_on", note=note.pitch, velocity=VELOCITY)))
            events.append((ticks(note.end), 0, mido.Message("note_off", note=note.pitch, velocity=0)))
        events.sort(key=lambda e: (e[0], e[1]))

        current = 0
        for tick, _, message in events:
            track.append(message.copy(time=tick - current))
            current = tick
        track.append(mido.MetaMessage("end_of_track", time=0))
        midi.tracks.append(track)
    midi.save(str(path))
