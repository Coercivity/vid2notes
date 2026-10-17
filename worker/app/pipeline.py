import tempfile
from collections.abc import Callable
from pathlib import Path

from app import analysis, extraction, pdf, video
from app.config import Settings
from app.messages import AnalysisCompleted, AnalyzeVideo, ExtractionCompleted, ExtractNotes
from app.storage import Storage

Report = Callable[[str, float], None]


def _scaled(report: Report, stage: str, low: float, high: float) -> Callable[[float], None]:
    return lambda fraction: report(stage, low + (high - low) * fraction)


def run_analyze(command: AnalyzeVideo, settings: Settings, storage: Storage, report: Report) -> AnalysisCompleted:
    with tempfile.TemporaryDirectory(dir=settings.work_dir) as tmp:
        work = Path(tmp)
        downloaded = video.download(
            command.url,
            work,
            settings.max_duration_seconds,
            _scaled(report, "downloading", 0, 40),
        )
        info = video.probe(downloaded.path)
        result = analysis.analyze(downloaded.path, info, _scaled(report, "analyzing", 40, 90))

        report("uploading", 90)
        video_key = f"videos/{command.job_id}{downloaded.path.suffix}"
        storage.upload_file(downloaded.path, video_key, "video/mp4")
        preview_keys = []
        for index, preview in enumerate(result.previews):
            key = f"previews/{command.job_id}/{index}.jpg"
            storage.upload_bytes(preview, key, "image/jpeg")
            preview_keys.append(key)

        return AnalysisCompleted(
            job_id=command.job_id,
            title=downloaded.title,
            duration_seconds=round(info.duration, 2),
            width=info.width,
            height=info.height,
            video_key=video_key,
            preview_keys=preview_keys,
            suggested_crop=result.crop,
            suggested_layout=result.layout,
        )


def run_extract(command: ExtractNotes, settings: Settings, storage: Storage, report: Report) -> ExtractionCompleted:
    with tempfile.TemporaryDirectory(dir=settings.work_dir) as tmp:
        work = Path(tmp)
        report("downloading", 0)
        source = work / f"source{Path(command.video_key).suffix}"
        storage.download_file(command.video_key, source)
        info = video.probe(source)

        start = max(command.start_seconds or 0.0, 0.0)
        end = min(command.end_seconds or info.duration, info.duration)
        if end <= start:
            raise video.PermanentError("End time must be greater than start time")

        fragments = extraction.extract(
            source,
            command.crop,
            command.layout,
            start,
            end,
            _scaled(report, "extracting", 10, 85),
        )

        report("rendering", 85)
        pages = pdf.compose(fragments)
        output = work / "notes.pdf"
        pdf.save_pdf(pages, output)

        report("uploading", 95)
        pdf_key = f"pdf/{command.job_id}.pdf"
        storage.upload_file(output, pdf_key, "application/pdf")
        return ExtractionCompleted(job_id=command.job_id, pdf_key=pdf_key, page_count=len(pages))
