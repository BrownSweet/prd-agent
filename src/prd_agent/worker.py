from __future__ import annotations

import logging
import time

from prd_agent.repositories import SQLAlchemyRepository
from prd_agent.services import JobRunner, ensure_default_llm_config
from prd_agent.settings import Settings

logger = logging.getLogger(__name__)


def run_worker(
    settings: Settings,
    *,
    once: bool = False,
) -> None:
    if not settings.database_url:
        raise ValueError("缺少 DATABASE_URL，请先完成数据库配置")
    repository = SQLAlchemyRepository.from_url(
        settings.database_url,
        connect_timeout=settings.database_connect_timeout_seconds,
        read_timeout=settings.database_read_timeout_seconds,
    )
    ensure_default_llm_config(repository, settings)
    interrupted = repository.fail_interrupted_jobs()
    if interrupted:
        logger.warning("已将 %s 个中断任务标记为失败", interrupted)

    runner = JobRunner(repository, settings)
    while True:
        job = repository.claim_next_job()
        if not job:
            if once:
                return
            time.sleep(settings.worker_poll_seconds)
            continue
        try:
            result = runner.run(job)
            repository.complete_job(job.id, result)
        except Exception as exc:
            logger.exception("任务 %s 执行失败", job.id)
            repository.fail_job(job.id, str(exc))
        if once:
            return
