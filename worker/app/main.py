import asyncio
import logging
import os
from collections.abc import Callable
from typing import Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.messages import (
    ANALYSIS_COMPLETED_QUEUE,
    ANALYZE_QUEUE,
    EXTRACT_QUEUE,
    EXTRACTION_COMPLETED_QUEUE,
    JOB_FAILED_QUEUE,
    OUTPUT_QUEUES,
    PROGRESS_QUEUE,
    AnalyzeVideo,
    ExtractNotes,
    JobFailed,
    JobProgress,
    Message,
)
from app.pipeline import run_analyze, run_extract
from app.storage import Storage
from app.video import PermanentError

log = logging.getLogger("worker")

ATTEMPT_HEADER = "x-attempt"


class Worker:
    def __init__(self, settings: Settings, storage: Storage, channel: aio_pika.abc.AbstractChannel):
        self._settings = settings
        self._storage = storage
        self._channel = channel
        self._loop = asyncio.get_running_loop()

    async def publish(self, queue: str, message: Message, headers: dict[str, Any] | None = None) -> None:
        await self._channel.default_exchange.publish(
            aio_pika.Message(
                body=message.to_json(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                headers=headers,
            ),
            routing_key=queue,
        )

    def _reporter(self, job_id: str) -> Callable[[str, float], None]:
        last: dict[str, Any] = {"stage": None, "percent": -100}

        def report(stage: str, percent: float) -> None:
            value = int(percent)
            if stage == last["stage"] and value - last["percent"] < 5:
                return
            last["stage"], last["percent"] = stage, value
            future = asyncio.run_coroutine_threadsafe(
                self.publish(PROGRESS_QUEUE, JobProgress(job_id=job_id, stage=stage, percent=value)),
                self._loop,
            )
            future.result()

        return report

    async def handle(
        self,
        message: AbstractIncomingMessage,
        queue: str,
        model: type[BaseModel],
        stage: str,
        run: Callable[..., Message],
        completed_queue: str,
    ) -> None:
        async with message.process(requeue=False):
            try:
                command = model.model_validate_json(message.body)
            except ValidationError:
                log.exception("Dropping malformed message from %s", queue)
                return

            job_id = command.job_id
            attempt = int((message.headers or {}).get(ATTEMPT_HEADER, 1))
            log.info("Job %s: %s started (attempt %d)", job_id, stage, attempt)
            try:
                result = await asyncio.to_thread(run, command, self._settings, self._storage, self._reporter(job_id))
                await self.publish(completed_queue, result)
                log.info("Job %s: %s completed", job_id, stage)
            except PermanentError as error:
                log.warning("Job %s: %s failed: %s", job_id, stage, error)
                await self.publish(JOB_FAILED_QUEUE, JobFailed(job_id=job_id, stage=stage, reason=str(error)))
            except Exception as error:
                log.exception("Job %s: %s attempt %d failed", job_id, stage, attempt)
                if attempt < self._settings.max_attempts:
                    await asyncio.sleep(5 * attempt)
                    await self._channel.default_exchange.publish(
                        aio_pika.Message(
                            body=message.body,
                            content_type="application/json",
                            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                            headers={ATTEMPT_HEADER: attempt + 1},
                        ),
                        routing_key=queue,
                    )
                else:
                    await self.publish(JOB_FAILED_QUEUE, JobFailed(job_id=job_id, stage=stage, reason=str(error)))


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings()
    os.makedirs(settings.work_dir, exist_ok=True)

    storage = Storage(settings)
    await asyncio.to_thread(storage.ensure_bucket)

    connection = await aio_pika.connect_robust(settings.rabbit_url)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1, global_=True)
        for name in OUTPUT_QUEUES:
            await channel.declare_queue(name, durable=True)

        worker = Worker(settings, storage, channel)
        analyze_queue = await channel.declare_queue(ANALYZE_QUEUE, durable=True)
        extract_queue = await channel.declare_queue(EXTRACT_QUEUE, durable=True)

        await analyze_queue.consume(
            lambda m: worker.handle(m, ANALYZE_QUEUE, AnalyzeVideo, "analyze", run_analyze, ANALYSIS_COMPLETED_QUEUE)
        )
        await extract_queue.consume(
            lambda m: worker.handle(m, EXTRACT_QUEUE, ExtractNotes, "extract", run_extract, EXTRACTION_COMPLETED_QUEUE)
        )
        log.info("Worker started")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
