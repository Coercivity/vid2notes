from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

ANALYZE_QUEUE = "analyze-video"
EXTRACT_QUEUE = "extract-notes"
PROGRESS_QUEUE = "job-progress"
ANALYSIS_COMPLETED_QUEUE = "analysis-completed"
EXTRACTION_COMPLETED_QUEUE = "extraction-completed"
JOB_FAILED_QUEUE = "job-failed"

OUTPUT_QUEUES = (PROGRESS_QUEUE, ANALYSIS_COMPLETED_QUEUE, EXTRACTION_COMPLETED_QUEUE, JOB_FAILED_QUEUE)


class Message(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    def to_json(self) -> bytes:
        return self.model_dump_json(by_alias=True).encode()


class Crop(Message):
    x: float
    y: float
    width: float
    height: float


class AnalyzeVideo(Message):
    job_id: str
    url: str


class ExtractNotes(Message):
    job_id: str
    video_key: str
    crop: Crop
    layout: str
    start_seconds: float | None = None
    end_seconds: float | None = None
    title: str | None = None
    tempo: float | None = None
    beats_per_bar: int | None = None


class JobProgress(Message):
    job_id: str
    stage: str
    percent: int


class AnalysisCompleted(Message):
    job_id: str
    title: str | None
    duration_seconds: float
    width: int
    height: int
    video_key: str
    preview_keys: list[str]
    suggested_crop: Crop
    suggested_layout: str


class ExtractionCompleted(Message):
    job_id: str
    pdf_key: str | None = None
    page_count: int | None = None
    midi_key: str | None = None
    note_count: int | None = None
    music_xml_key: str | None = None
    tempo: float | None = None
    time_signature: str | None = None
    key_name: str | None = None


class JobFailed(Message):
    job_id: str
    stage: str
    reason: str
