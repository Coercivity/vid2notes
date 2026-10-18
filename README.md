# vid2notes

A service that extracts sheet music from videos (YouTube or any link supported by yt-dlp) and assembles it into a PDF.

## Architecture

```
Client ──HTTP──► Vid2Notes.Api (ASP.NET 8) ──► PostgreSQL
                    │  ▲
     analyze-video  │  │ job-progress / analysis-completed /
     extract-notes  │  │ extraction-completed / job-failed
                    ▼  │
                 RabbitMQ
                    │
                    ▼
             worker (Python) ──► S3 / SeaweedFS (videos, previews, PDFs)
```

- **API** is the sole owner of the database. Commands are sent through MassTransit with the EF Outbox, and messages use raw JSON (camelCase).
- **Worker** is stateless and processes one job at a time (`prefetch=1`). Scale it by adding replicas.
- **S3 storage**: `videos/{jobId}.*`, `previews/{jobId}/{n}.jpg`, `pdf/{jobId}.pdf`. Locally this is SeaweedFS (MinIO images are no longer published); any S3-compatible storage works in production.

## Two-phase processing

1. `POST /jobs` → the worker downloads the video, detects the staves, suggests a crop area (`suggestedCrop`) and a video type (`suggestedLayout`: `pages`, `scroll` or `synthesia`), and saves preview frames. Status becomes `awaitingCrop`.
2. The user reviews the previews (`GET /jobs/{id}/previews/{n}`) and confirms or adjusts the area.
3. `POST /jobs/{id}/extract` → the worker builds the PDF. Status becomes `completed`, and the file is available at `GET /jobs/{id}/pdf`.

Statuses: `analyzing → awaitingCrop → extracting → completed | failed`. Extraction can be restarted with a different area from `awaitingCrop`, `completed` or `failed`.

### Video types

- **pages**: the music changes page by page or line by line. Stable segments are kept, the cursor and highlights are removed with a per-pixel median across frames, duplicates are dropped, and pages that fill in gradually replace their earlier version.
- **scroll**: the music scrolls horizontally. The shift between frames is found with phase correlation, the strip is stitched together and cut into lines where there is the least "ink".

- **synthesia**: falling notes over a piano keyboard. Both rendered Synthesia videos and overlays on a filmed piano are supported. The keyboard is located by its black-key pattern using a locally adaptive brightness threshold, which gives every key's position and pitch (88, 76, 61 and 49 key layouts are recognised; other sizes are centred on middle C). The bottom edge of the falling area is found above any decorative strip (felt, glowing line, metal bar). Every frame is sampled in two ways: key highlight colour and bar cores on probe lines just above that edge. Keys are used when their highlights agree with arriving bars; otherwise notes are read from the bars, whose lanes are fitted to the keyboard (scale, shift and per pitch-class offsets) from all detected bars. Repeated notes are split on gaps between bars, shadows and twins on neighbouring lanes are removed, and note colours are clustered into left and right hands.

  The notes are then turned into notation: the tempo and grid (sixteenths or triplets) are fitted to the onsets, the bar length and downbeat come from bass and accent positions, durations are quantised and slightly legato-normalised, and the key is estimated with Krumhansl-Schmuckler profiles. music21 builds a two-staff score (right hand / left hand), Verovio engraves it and CairoSVG produces the PDF. Tempo and beats per bar can be overridden in the extract request (`tempo`, `beatsPerBar`). Outputs: PDF, MIDI (`GET /jobs/{id}/midi`) and MusicXML (`GET /jobs/{id}/musicxml`) for editing in MuseScore.

## Running

```bash
docker compose up -d --build
```

- Web UI: http://localhost:3000
- API and Swagger: http://localhost:8080/swagger
- PostgreSQL: localhost:5433 (vid2notes / vid2notes)
- RabbitMQ: http://localhost:15672 (guest / guest)
- S3 (SeaweedFS): http://localhost:8333

Scaling workers:

```bash
docker compose up -d --scale worker=3
```

## Example

```bash
curl -X POST http://localhost:8080/jobs -H "Content-Type: application/json" -d '{"url":"https://www.youtube.com/watch?v=..."}'
curl http://localhost:8080/jobs/{id}
curl -X POST http://localhost:8080/jobs/{id}/extract -H "Content-Type: application/json" -d '{"crop":{"x":0.1,"y":0.05,"width":0.8,"height":0.9},"layout":"pages","startSeconds":5}'
curl -o notes.pdf http://localhost:8080/jobs/{id}/pdf
```

An empty `extract` body (`{}`) uses the suggested area and type.

## Frontend

React + Vite + TypeScript in `web/`. Progress is updated by polling `GET /jobs/{id}`, and the sheet music area is selected with the mouse directly on the preview. In Docker, nginx serves the static files and proxies `/jobs` to the API.

Local development (the API must be running on :8080):

```bash
cd web
npm install
npm run dev
```

## Migrations

```bash
dotnet tool restore
dotnet ef migrations add <Name> -p src/Vid2Notes.Api -o Data/Migrations
```

Migrations are applied when the API starts.
