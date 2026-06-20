from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timezone

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from prd_agent.models import (
    ArtifactType,
    AuditEvent,
    JobStatus,
    JobType,
    ProjectState,
    Stage,
)
from prd_agent.repositories import (
    ActiveJobError,
    ArtifactRecord,
    ProjectRecord,
    RequirementSnapshotRecord,
    SQLAlchemyRepository,
    WorkflowJobRecord,
    WorkflowEventRecord,
)
from prd_agent.services import JobRunner
from prd_agent.settings import Settings


def test_mysql_json_and_utc_round_trip(
    repository: SQLAlchemyRepository,
) -> None:
    state = ProjectState()
    state.requirement_spec.assumptions = ["JSON往返"]
    repository.create_project(state)

    restored = repository.get_project(state.project_id)
    assert restored.requirement_spec.assumptions == ["JSON往返"]
    assert restored.created_at.tzinfo == timezone.utc
    assert restored.updated_at.tzinfo == timezone.utc

    long_content = "长" * 70_000
    artifact = repository.save_artifact(
        state.project_id,
        ArtifactType.PRD,
        long_content,
        {"nested": {"enabled": True}},
    )
    record = repository.get_latest_artifact(state.project_id, ArtifactType.PRD)
    assert record.content == long_content
    assert record.metadata_json == {"nested": {"enabled": True}}
    assert artifact.created_at.tzinfo == timezone.utc
    assert record.created_at.tzinfo == timezone.utc


def test_mysql_cascade_delete_removes_project_children(
    repository: SQLAlchemyRepository,
) -> None:
    state = ProjectState()
    repository.create_project(state)
    repository.save_requirement_snapshot(state)
    repository.save_artifact(state.project_id, ArtifactType.PRD, "content")
    repository.add_event(
        state.project_id,
        AuditEvent(
            event_type="test",
            stage=Stage.STRUCTURING,
            message="test",
        ),
    )

    with repository.sessions.begin() as session:
        session.execute(delete(ProjectRecord).where(ProjectRecord.id == state.project_id))

    with repository.sessions() as session:
        assert session.scalar(
            select(func.count()).select_from(RequirementSnapshotRecord)
        ) == 0
        assert session.scalar(select(func.count()).select_from(ArtifactRecord)) == 0
        assert session.scalar(
            select(func.count()).select_from(WorkflowEventRecord)
        ) == 0


def test_mysql_unique_constraint_and_transaction_rollback(
    repository: SQLAlchemyRepository,
) -> None:
    state = ProjectState()
    repository.create_project(state)
    repository.save_requirement_snapshot(state)

    with pytest.raises(IntegrityError):
        with repository.sessions.begin() as session:
            session.add(
                RequirementSnapshotRecord(
                    project_id=state.project_id,
                    version=1,
                    requirement_json={},
                )
            )

    rolled_back = ProjectState()
    with pytest.raises(RuntimeError, match="rollback"):
        with repository.sessions.begin() as session:
            session.add(
                ProjectRecord(
                    id=rolled_back.project_id,
                    stage=str(rolled_back.stage),
                    stage_status=str(rolled_back.stage_status),
                    state_json=rolled_back.model_dump(mode="json", by_alias=True),
                    created_at=rolled_back.created_at,
                    updated_at=rolled_back.updated_at,
                )
            )
            raise RuntimeError("rollback")

    with repository.sessions() as session:
        assert session.get(ProjectRecord, rolled_back.project_id) is None


def test_mysql_concurrent_artifact_versions_are_serialized(
    repository: SQLAlchemyRepository,
) -> None:
    state = ProjectState()
    repository.create_project(state)

    def save(index: int) -> int:
        return repository.save_artifact(
            state.project_id,
            ArtifactType.PRD,
            f"content-{index}",
        ).version

    with ThreadPoolExecutor(max_workers=5) as executor:
        versions = list(executor.map(save, range(5)))

    assert sorted(versions) == [1, 2, 3, 4, 5]
    with repository.sessions() as session:
        stored = list(
            session.scalars(
                select(ArtifactRecord.version)
                .where(ArtifactRecord.project_id == state.project_id)
                .order_by(ArtifactRecord.version)
            )
        )
    assert stored == [1, 2, 3, 4, 5]


def test_mysql_concurrent_requirement_versions_are_serialized(
    repository: SQLAlchemyRepository,
) -> None:
    state = ProjectState()
    repository.create_project(state)

    with ThreadPoolExecutor(max_workers=5) as executor:
        versions = list(
            executor.map(
                lambda _: repository.save_requirement_snapshot(state),
                range(5),
            )
        )

    assert sorted(versions) == [1, 2, 3, 4, 5]
    with repository.sessions() as session:
        stored = list(
            session.scalars(
                select(RequirementSnapshotRecord.version)
                .where(RequirementSnapshotRecord.project_id == state.project_id)
                .order_by(RequirementSnapshotRecord.version)
            )
        )
    assert stored == [1, 2, 3, 4, 5]


def test_mysql_job_queue_is_idempotent_and_project_exclusive(
    repository: SQLAlchemyRepository,
) -> None:
    config = repository.create_llm_config(
        name="queue-test",
        provider="deepseek",
        model="deepseek-chat",
        api_key="secret",
        base_url=None,
        temperature=0.2,
        timeout_seconds=120,
        native_structured_output=False,
    )
    state = ProjectState()
    repository.create_project(state, llm_config_id=config.id)

    first = repository.enqueue_job(
        job_type=JobType.WORKFLOW,
        idempotency_key="queue-test-key-001",
        payload={"operation": "advance"},
        project_id=state.project_id,
        llm_config_id=config.id,
        llm_config_version=config.version,
    )
    repeated = repository.enqueue_job(
        job_type=JobType.WORKFLOW,
        idempotency_key="queue-test-key-001",
        payload={"operation": "ignored"},
        project_id=state.project_id,
        llm_config_id=config.id,
        llm_config_version=config.version,
    )

    assert first.id == repeated.id
    assert first.status == str(JobStatus.QUEUED)
    with pytest.raises(ActiveJobError, match="已有"):
        repository.enqueue_job(
            job_type=JobType.WORKFLOW,
            idempotency_key="queue-test-key-002",
            payload={"operation": "advance"},
            project_id=state.project_id,
            llm_config_id=config.id,
            llm_config_version=config.version,
        )

    claimed = repository.claim_next_job()
    assert claimed is not None
    assert claimed.id == first.id
    assert claimed.status == str(JobStatus.RUNNING)
    repository.complete_job(claimed.id, {"ok": True})

    second = repository.enqueue_job(
        job_type=JobType.WORKFLOW,
        idempotency_key="queue-test-key-002",
        payload={"operation": "advance"},
        project_id=state.project_id,
        llm_config_id=config.id,
        llm_config_version=config.version,
    )
    assert second.id != first.id


def test_mysql_claim_next_job_does_not_double_claim(
    repository: SQLAlchemyRepository,
) -> None:
    config = repository.create_llm_config(
        name="claim-test",
        provider="deepseek",
        model="deepseek-chat",
        api_key="secret",
        base_url=None,
        temperature=0.2,
        timeout_seconds=120,
        native_structured_output=False,
    )
    project_ids: list[str] = []
    for index in range(2):
        state = ProjectState()
        repository.create_project(state, llm_config_id=config.id)
        project_ids.append(state.project_id)
        repository.enqueue_job(
            job_type=JobType.WORKFLOW,
            idempotency_key=f"claim-test-key-{index:03d}",
            payload={"operation": "advance"},
            project_id=state.project_id,
            llm_config_id=config.id,
            llm_config_version=config.version,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claimed = list(executor.map(lambda _: repository.claim_next_job(), range(2)))

    claimed_ids = {job.id for job in claimed if job is not None}
    assert len(claimed_ids) == 2


def test_job_runner_rejects_changed_llm_config(
    repository: SQLAlchemyRepository,
    test_database_url: str,
) -> None:
    config = repository.create_llm_config(
        name="version-test",
        provider="deepseek",
        model="deepseek-chat",
        api_key="secret",
        base_url=None,
        temperature=0.2,
        timeout_seconds=120,
        native_structured_output=False,
    )
    job = repository.enqueue_job(
        job_type=JobType.LLM_TEST,
        idempotency_key="version-test-key-001",
        payload={},
        llm_config_id=config.id,
        llm_config_version=config.version,
    )
    repository.update_llm_config(
        config.id,
        name=config.name,
        provider=config.provider,
        model=config.model,
        api_key=None,
        update_api_key=False,
        base_url=config.base_url,
        temperature=0.3,
        timeout_seconds=config.timeout_seconds,
        native_structured_output=config.native_structured_output,
        make_default=False,
        archived=False,
    )
    url = make_url(test_database_url)
    settings = Settings(
        _env_file=None,
        database_url=test_database_url,
        test_database_url=url.set(
            database=f"{url.database}_other_test"
        ).render_as_string(hide_password=False),
        llm_model="deepseek/deepseek-chat",
        llm_api_key="secret",
    )

    with pytest.raises(ValueError, match="发生变化"):
        JobRunner(repository, settings)._load_versioned_config(job)
