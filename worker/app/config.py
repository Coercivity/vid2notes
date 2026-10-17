import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    rabbit_url: str = field(default_factory=lambda: os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"))
    s3_endpoint: str = field(default_factory=lambda: os.getenv("S3_ENDPOINT", "http://localhost:8333"))
    s3_access_key: str = field(default_factory=lambda: os.getenv("S3_ACCESS_KEY", "vid2notes"))
    s3_secret_key: str = field(default_factory=lambda: os.getenv("S3_SECRET_KEY", "vid2notes"))
    s3_bucket: str = field(default_factory=lambda: os.getenv("S3_BUCKET", "vid2notes"))
    max_duration_seconds: int = field(default_factory=lambda: int(os.getenv("MAX_DURATION_SECONDS", "1800")))
    max_attempts: int = field(default_factory=lambda: int(os.getenv("MAX_ATTEMPTS", "3")))
    work_dir: str = field(default_factory=lambda: os.getenv("WORK_DIR", "/tmp/vid2notes"))
