from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import yt_dlp

FORMAT = (
    "bv*[height<=1080][vcodec^=avc1]/"
    "bv*[height<=1080][ext=mp4]/"
    "bv*[height<=1080]/"
    "b[height<=1080]/b"
)


class PermanentError(Exception):
    pass


class VideoTooLongError(PermanentError):
    pass


@dataclass(frozen=True)
class DownloadedVideo:
    path: Path
    title: str | None


@dataclass(frozen=True)
class VideoInfo:
    fps: float
    frame_count: int
    width: int
    height: int

    @property
    def duration(self) -> float:
        return self.frame_count / self.fps


def download(url: str, target_dir: Path, max_duration: int, on_progress: Callable[[float], None]) -> DownloadedVideo:
    def hook(d: dict) -> None:
        if d.get("status") != "downloading":
            return
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        if total:
            on_progress(min(d.get("downloaded_bytes", 0) / total, 1.0))

    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": FORMAT,
        "outtmpl": str(target_dir / "source.%(ext)s"),
        "progress_hooks": [hook],
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
        duration = info.get("duration")
        if duration and duration > max_duration:
            raise VideoTooLongError(f"Video is {int(duration)}s long, limit is {max_duration}s")
        info = ydl.process_ie_result(info, download=True)
        path = Path(info["requested_downloads"][0]["filepath"])
        return DownloadedVideo(path=path, title=info.get("title"))


def probe(path: Path) -> VideoInfo:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise PermanentError("Unable to open video")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        return VideoInfo(
            fps=fps,
            frame_count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
    finally:
        cap.release()


def sample_frames(
    path: Path,
    step_seconds: float,
    start: float | None = None,
    end: float | None = None,
) -> Iterator[tuple[float, np.ndarray]]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise PermanentError("Unable to open video")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        index = 0
        if start:
            index = int(start * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        next_time = index / fps
        while cap.grab():
            time = index / fps
            index += 1
            if end is not None and time > end:
                break
            if time + 1e-6 < next_time:
                continue
            ok, frame = cap.retrieve()
            if ok:
                yield time, frame
            while step_seconds > 0 and next_time <= time + 1e-6:
                next_time += step_seconds
    finally:
        cap.release()
