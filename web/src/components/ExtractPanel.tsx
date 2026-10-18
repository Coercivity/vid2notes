import { useEffect, useState } from "react";
import { api, Crop, Job, SheetLayout } from "../api";
import { formatTime, parseTime } from "../time";
import { CropEditor } from "./CropEditor";

interface Props {
  job: Job;
  onStarted: (job: Job) => void;
}

const FULL_FRAME: Crop = { x: 0, y: 0, width: 1, height: 1 };

const LAYOUTS: { value: SheetLayout; label: string; hint: string }[] = [
  { value: "pages", label: "Pages", hint: "music changes page by page or line by line" },
  { value: "scroll", label: "Scroll", hint: "music scrolls horizontally as a strip" },
  { value: "synthesia", label: "Synthesia", hint: "falling notes over a piano keyboard, transcribed to notation" },
];

const BEATS_PER_BAR = [2, 3, 4, 6];

export function ExtractPanel({ job, onStarted }: Props) {
  const [crop, setCrop] = useState<Crop>(job.crop ?? job.suggestedCrop ?? FULL_FRAME);
  const [layout, setLayout] = useState<SheetLayout>(job.layout ?? job.suggestedLayout ?? "pages");
  const [start, setStart] = useState(formatTime(job.startSeconds));
  const [end, setEnd] = useState(formatTime(job.endSeconds));
  const [tempo, setTempo] = useState("");
  const [beatsPerBar, setBeatsPerBar] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setCrop(job.crop ?? job.suggestedCrop ?? FULL_FRAME);
    setLayout(job.layout ?? job.suggestedLayout ?? "pages");
  }, [job.id]);

  const submit = async () => {
    const startSeconds = parseTime(start);
    const endSeconds = parseTime(end);
    if (startSeconds === undefined || endSeconds === undefined) {
      setError("Use m:ss or seconds for time");
      return;
    }
    const bpm = tempo.trim() ? Number(tempo) : null;
    if (bpm !== null && (Number.isNaN(bpm) || bpm < 20 || bpm > 300)) {
      setError("Tempo must be between 20 and 300 BPM");
      return;
    }
    const synthesia = layout === "synthesia";
    setBusy(true);
    setError(null);
    try {
      onStarted(
        await api.extract(job.id, {
          crop,
          layout,
          startSeconds,
          endSeconds,
          tempo: synthesia ? bpm : null,
          beatsPerBar: synthesia && beatsPerBar ? Number(beatsPerBar) : null,
        }),
      );
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <h2>{layout === "synthesia" ? "Piano keyboard" : "Sheet music area"}</h2>
      <p className="muted">
        {layout === "synthesia"
          ? "Put the box around the piano keyboard. "
          : "Drag the box or its edges, or draw a new area with the mouse. "}
        Use the frames below to check the box across the whole video.
      </p>
      <CropEditor previews={job.previews} crop={crop} onChange={setCrop} />

      <div className="options">
        <fieldset>
          <legend>Video type</legend>
          {LAYOUTS.map((option) => (
            <label key={option.value} className="radio">
              <input
                type="radio"
                name="layout"
                value={option.value}
                checked={layout === option.value}
                onChange={() => setLayout(option.value)}
              />
              <span>
                {option.label}
                {job.suggestedLayout === option.value && <em className="badge">suggested</em>}
                <small className="muted">{option.hint}</small>
              </span>
            </label>
          ))}
        </fieldset>

        <fieldset>
          <legend>Video range</legend>
          <div className="time-range">
            <label>
              from
              <input placeholder="0:00" value={start} onChange={(e) => setStart(e.target.value)} />
            </label>
            <label>
              to
              <input placeholder={formatTime(job.durationSeconds) || "end"} value={end} onChange={(e) => setEnd(e.target.value)} />
            </label>
          </div>
        </fieldset>

        {layout === "synthesia" && (
          <fieldset>
            <legend>Notation</legend>
            <div className="time-range">
              <label>
                tempo
                <input
                  inputMode="decimal"
                  placeholder={job.tempo ? String(Math.round(job.tempo)) : "auto"}
                  value={tempo}
                  onChange={(e) => setTempo(e.target.value)}
                />
                BPM
              </label>
              <label>
                beats per bar
                <select value={beatsPerBar} onChange={(e) => setBeatsPerBar(e.target.value)}>
                  <option value="">auto</option>
                  {BEATS_PER_BAR.map((beats) => (
                    <option key={beats} value={beats}>
                      {beats}/4
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <small className="muted">Leave empty to detect automatically. Set them if the bars come out wrong.</small>
          </fieldset>
        )}
      </div>

      <div className="actions">
        {job.suggestedCrop && (
          <button type="button" onClick={() => setCrop(job.suggestedCrop!)} disabled={busy}>
            Reset to suggested area
          </button>
        )}
        <button type="button" onClick={() => setCrop(FULL_FRAME)} disabled={busy}>
          Full frame
        </button>
        <button className="primary" type="button" onClick={submit} disabled={busy}>
          {busy ? "Starting…" : `${job.status === "completed" ? "Rebuild" : "Build"} sheet music`}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
