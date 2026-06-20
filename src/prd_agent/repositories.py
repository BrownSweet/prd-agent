from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.dialects.mysql import JSON, LONGTEXT
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)
from sqlalchemy.types import TypeDecorator

from prd_agent.models import (
    ArtifactType,
    ArtifactVersion,
    AuditEvent,
    JobStatus,
    JobType,
    ProjectState,
    utc_now,
)


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator[datetime]):
    """Persist UTC as MySQL DATETIME and restore timezone information on read."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(
        self,
        value: datetime | None,
        dialect: Any,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).replace(tzinfo=None)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(
        self,
        value: datetime | None,
        dialect: Any,
    ) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


MYSQL_TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return str(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _json_ready(model_dump(mode="json", by_alias=True))
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return value


class ProjectRecord(Base):
    __tablename__ = "projects"
    __table_args__ = MYSQL_TABLE_OPTIONS

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    stage: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    stage_status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    llm_config_id: Mapped[str | None] = mapped_column(
        ForeignKey("llm_configs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True, index=True
    )
    state_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, index=True
    )


class RequirementSnapshotRecord(Base):
    __tablename__ = "requirement_snapshots"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_requirement_version"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    requirement_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now
    )


class QuestionRecord(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("project_id", "question_id", name="uq_project_question"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[str] = mapped_column(String(16), nullable=False)
    question_type: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    answer: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now
    )


class LogicIssueRecord(Base):
    __tablename__ = "logic_issues"
    __table_args__ = (
        UniqueConstraint("project_id", "issue_id", name="uq_project_logic_issue"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    issue_id: Mapped[str] = mapped_column(String(16), nullable=False)
    dimension: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    resolution: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now
    )


class ArtifactRecord(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "artifact_type", "version", name="uq_artifact_version"
        ),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    artifact_type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now
    )


class ApprovalRecord(Base):
    __tablename__ = "approvals"
    __table_args__ = MYSQL_TABLE_OPTIONS

    approval_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    artifact_version: Mapped[int | None] = mapped_column(Integer)
    approved_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class WorkflowEventRecord(Base):
    __tablename__ = "workflow_events"
    __table_args__ = MYSQL_TABLE_OPTIONS

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class LlmConfigRecord(Base):
    __tablename__ = "llm_configs"
    __table_args__ = (
        UniqueConstraint("name", name="uq_llm_config_name"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key: Mapped[str | None] = mapped_column(LONGTEXT)
    base_url: Mapped[str | None] = mapped_column(String(500))
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    native_structured_output: Mapped[bool | None] = mapped_column(Boolean)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class WorkflowJobRecord(Base):
    __tablename__ = "workflow_jobs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_job_idempotency_key"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    job_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    result_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    llm_config_id: Mapped[str | None] = mapped_column(
        ForeignKey("llm_configs.id", ondelete="SET NULL"),
        nullable=True,
    )
    llm_config_version: Mapped[int | None] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class AppSettingRecord(Base):
    __tablename__ = "app_settings"
    __table_args__ = MYSQL_TABLE_OPTIONS

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ProjectNotFoundError(LookupError):
    pass


class ArtifactNotFoundError(LookupError):
    pass


class LlmConfigNotFoundError(LookupError):
    pass


class ActiveJobError(RuntimeError):
    pass


class SQLAlchemyRepository:
    def __init__(self, engine: Engine):
        if engine.dialect.name != "mysql" or engine.dialect.driver != "pymysql":
            raise ValueError("Repository仅支持MySQL 8.0+和PyMySQL驱动")
        self.engine = engine
        self.sessions = sessionmaker(
            bind=engine,
            class_=Session,
            expire_on_commit=False,
        )

    @classmethod
    def from_url(
        cls,
        database_url: str,
        connect_timeout: int = 5,
        read_timeout: int = 30,
    ) -> SQLAlchemyRepository:
        url = make_url(database_url)
        if url.get_backend_name() != "mysql":
            raise ValueError("仅支持MySQL数据库")
        if url.drivername != "mysql+pymysql":
            raise ValueError("MySQL连接必须使用PyMySQL驱动")
        if url.query.get("charset") != "utf8mb4":
            raise ValueError("MySQL连接必须包含 charset=utf8mb4")
        return cls(
            create_engine(
                database_url,
                pool_pre_ping=True,
                pool_recycle=1800,
                connect_args={
                    "connect_timeout": connect_timeout,
                    "read_timeout": read_timeout,
                    "write_timeout": read_timeout,
                },
            )
        )

    def create_project(
        self,
        state: ProjectState,
        llm_config_id: str | None = None,
    ) -> None:
        state.updated_at = utc_now()
        with self.sessions.begin() as session:
            session.add(
                ProjectRecord(
                    id=state.project_id,
                    stage=str(state.stage),
                    stage_status=str(state.stage_status),
                    llm_config_id=llm_config_id,
                    archived_at=None,
                    state_json=state.model_dump(mode="json", by_alias=True),
                    created_at=state.created_at,
                    updated_at=state.updated_at,
                )
            )

    def get_project(self, project_id: str) -> ProjectState:
        with self.sessions() as session:
            record = session.get(ProjectRecord, project_id)
            if not record:
                raise ProjectNotFoundError(f"项目不存在：{project_id}")
            return ProjectState.model_validate(record.state_json)

    def get_project_record(self, project_id: str) -> ProjectRecord:
        with self.sessions() as session:
            record = session.get(ProjectRecord, project_id)
            if not record:
                raise ProjectNotFoundError(f"项目不存在：{project_id}")
            session.expunge(record)
            return record

    def list_projects(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str = "",
        archived: bool = False,
    ) -> tuple[list[ProjectRecord], int]:
        with self.sessions() as session:
            records = list(
                session.scalars(
                    select(ProjectRecord)
                    .where(
                        ProjectRecord.archived_at.is_not(None)
                        if archived
                        else ProjectRecord.archived_at.is_(None)
                    )
                    .order_by(ProjectRecord.updated_at.desc())
                )
            )
            if search:
                needle = search.casefold()
                records = [
                    record
                    for record in records
                    if needle in record.id.casefold()
                    or needle
                    in str(
                        record.state_json.get("requirementSpec", {}).get(
                            "title", ""
                        )
                    ).casefold()
                ]
            total = len(records)
            start = (page - 1) * page_size
            selected = records[start : start + page_size]
            for record in selected:
                session.expunge(record)
            return selected, total

    def archive_project(self, project_id: str, archived: bool) -> ProjectRecord:
        with self.sessions.begin() as session:
            record = self._lock_project(session, project_id)
            if self._has_active_job(session, project_id):
                raise ActiveJobError("项目有运行中任务，不能归档")
            record.archived_at = utc_now() if archived else None
            record.updated_at = utc_now()
        return self.get_project_record(project_id)

    def set_project_llm_config(
        self,
        project_id: str,
        llm_config_id: str,
    ) -> None:
        with self.sessions.begin() as session:
            record = self._lock_project(session, project_id)
            config = session.get(LlmConfigRecord, llm_config_id)
            if not config or config.archived_at:
                raise LlmConfigNotFoundError(
                    f"LLM配置不存在或已归档：{llm_config_id}"
                )
            if self._has_active_job(session, project_id):
                raise ActiveJobError("项目有运行中任务，不能切换LLM配置")
            record.llm_config_id = llm_config_id
            record.updated_at = utc_now()

    def save_project(self, state: ProjectState) -> None:
        state.updated_at = utc_now()
        with self.sessions.begin() as session:
            record = session.get(ProjectRecord, state.project_id)
            if not record:
                raise ProjectNotFoundError(f"项目不存在：{state.project_id}")
            record.stage = str(state.stage)
            record.stage_status = str(state.stage_status)
            record.state_json = state.model_dump(mode="json", by_alias=True)
            record.updated_at = state.updated_at
            self._sync_questions(session, state)
            self._sync_logic_issues(session, state)
            self._sync_approvals(session, state)

    def save_requirement_snapshot(self, state: ProjectState) -> int:
        with self.sessions.begin() as session:
            self._lock_project(session, state.project_id)
            version = (
                session.scalar(
                    select(func.max(RequirementSnapshotRecord.version)).where(
                        RequirementSnapshotRecord.project_id == state.project_id
                    )
                )
                or 0
            ) + 1
            session.add(
                RequirementSnapshotRecord(
                    project_id=state.project_id,
                    version=version,
                    requirement_json=state.requirement_spec.model_dump(
                        mode="json", by_alias=True
                    ),
                )
            )
            return version

    def save_artifact(
        self,
        project_id: str,
        artifact_type: ArtifactType,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactVersion:
        with self.sessions.begin() as session:
            self._lock_project(session, project_id)
            version = (
                session.scalar(
                    select(func.max(ArtifactRecord.version)).where(
                        ArtifactRecord.project_id == project_id,
                        ArtifactRecord.artifact_type == str(artifact_type),
                    )
                )
                or 0
            ) + 1
            created_at = utc_now()
            session.add(
                ArtifactRecord(
                    project_id=project_id,
                    artifact_type=str(artifact_type),
                    version=version,
                    content=content,
                    metadata_json=_json_ready(metadata or {}),
                    created_at=created_at,
                )
            )
            return ArtifactVersion(
                artifact_type=artifact_type,
                version=version,
                created_at=created_at,
            )

    @staticmethod
    def _lock_project(session: Session, project_id: str) -> ProjectRecord:
        record = session.scalar(
            select(ProjectRecord)
            .where(ProjectRecord.id == project_id)
            .with_for_update()
        )
        if not record:
            raise ProjectNotFoundError(f"项目不存在：{project_id}")
        return record

    def get_latest_artifact(
        self, project_id: str, artifact_type: ArtifactType
    ) -> ArtifactRecord:
        with self.sessions() as session:
            record = session.scalar(
                select(ArtifactRecord)
                .where(
                    ArtifactRecord.project_id == project_id,
                    ArtifactRecord.artifact_type == str(artifact_type),
                )
                .order_by(ArtifactRecord.version.desc())
                .limit(1)
            )
            if not record:
                raise ArtifactNotFoundError(
                    f"项目 {project_id} 没有 {artifact_type} 文档"
                )
            session.expunge(record)
            return record

    def list_artifacts(self, project_id: str) -> list[ArtifactRecord]:
        with self.sessions() as session:
            records = list(
                session.scalars(
                    select(ArtifactRecord)
                    .where(ArtifactRecord.project_id == project_id)
                    .order_by(
                        ArtifactRecord.artifact_type,
                        ArtifactRecord.version.desc(),
                    )
                )
            )
            for record in records:
                session.expunge(record)
            return records

    def get_artifact(
        self,
        project_id: str,
        artifact_type: ArtifactType,
        version: int,
    ) -> ArtifactRecord:
        with self.sessions() as session:
            record = session.scalar(
                select(ArtifactRecord).where(
                    ArtifactRecord.project_id == project_id,
                    ArtifactRecord.artifact_type == str(artifact_type),
                    ArtifactRecord.version == version,
                )
            )
            if not record:
                raise ArtifactNotFoundError(
                    f"项目 {project_id} 没有 {artifact_type} v{version}"
                )
            session.expunge(record)
            return record

    def create_llm_config(
        self,
        *,
        name: str,
        provider: str,
        model: str,
        api_key: str | None,
        base_url: str | None,
        temperature: float,
        timeout_seconds: int,
        native_structured_output: bool | None,
        make_default: bool = False,
    ) -> LlmConfigRecord:
        now = utc_now()
        with self.sessions.begin() as session:
            if make_default:
                session.execute(update(LlmConfigRecord).values(is_default=False))
            record = LlmConfigRecord(
                id=str(uuid4()),
                name=name,
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
                native_structured_output=native_structured_output,
                version=1,
                is_default=make_default,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
        return self.get_llm_config(record.id)

    def update_llm_config(
        self,
        config_id: str,
        *,
        name: str,
        provider: str,
        model: str,
        api_key: str | None,
        update_api_key: bool,
        base_url: str | None,
        temperature: float,
        timeout_seconds: int,
        native_structured_output: bool | None,
        make_default: bool,
        archived: bool,
    ) -> LlmConfigRecord:
        with self.sessions.begin() as session:
            record = session.get(
                LlmConfigRecord,
                config_id,
                with_for_update=True,
            )
            if not record:
                raise LlmConfigNotFoundError(f"LLM配置不存在：{config_id}")
            if archived and (record.is_default or make_default):
                raise ValueError("默认LLM配置不能归档，请先设置其他默认配置")
            if make_default:
                session.execute(
                    update(LlmConfigRecord)
                    .where(LlmConfigRecord.id != config_id)
                    .values(is_default=False)
                )
            record.name = name
            record.provider = provider
            record.model = model
            if update_api_key:
                record.api_key = api_key
            record.base_url = base_url
            record.temperature = temperature
            record.timeout_seconds = timeout_seconds
            record.native_structured_output = native_structured_output
            record.is_default = make_default
            record.archived_at = utc_now() if archived else None
            record.version += 1
            record.updated_at = utc_now()
        return self.get_llm_config(config_id)

    def get_llm_config(self, config_id: str) -> LlmConfigRecord:
        with self.sessions() as session:
            record = session.get(LlmConfigRecord, config_id)
            if not record:
                raise LlmConfigNotFoundError(f"LLM配置不存在：{config_id}")
            session.expunge(record)
            return record

    def get_default_llm_config(self) -> LlmConfigRecord | None:
        with self.sessions() as session:
            record = session.scalar(
                select(LlmConfigRecord)
                .where(
                    LlmConfigRecord.is_default.is_(True),
                    LlmConfigRecord.archived_at.is_(None),
                )
                .order_by(LlmConfigRecord.updated_at.desc())
                .limit(1)
            )
            if record:
                session.expunge(record)
            return record

    def list_llm_configs(self, include_archived: bool = False) -> list[LlmConfigRecord]:
        with self.sessions() as session:
            statement = select(LlmConfigRecord)
            if not include_archived:
                statement = statement.where(LlmConfigRecord.archived_at.is_(None))
            records = list(
                session.scalars(
                    statement.order_by(
                        LlmConfigRecord.is_default.desc(),
                        LlmConfigRecord.updated_at.desc(),
                    )
                )
            )
            for record in records:
                session.expunge(record)
            return records

    def enqueue_job(
        self,
        *,
        job_type: JobType,
        idempotency_key: str,
        payload: dict[str, Any],
        project_id: str | None = None,
        llm_config_id: str | None = None,
        llm_config_version: int | None = None,
    ) -> WorkflowJobRecord:
        now = utc_now()
        with self.sessions.begin() as session:
            existing = session.scalar(
                select(WorkflowJobRecord).where(
                    WorkflowJobRecord.idempotency_key == idempotency_key
                )
            )
            if existing:
                session.expunge(existing)
                return existing
            if project_id:
                self._lock_project(session, project_id)
                if self._has_active_job(session, project_id):
                    raise ActiveJobError("项目已有排队或运行中的任务")
            record = WorkflowJobRecord(
                id=str(uuid4()),
                project_id=project_id,
                job_type=str(job_type),
                status=str(JobStatus.QUEUED),
                payload_json=_json_ready(payload),
                result_json={},
                llm_config_id=llm_config_id,
                llm_config_version=llm_config_version,
                idempotency_key=idempotency_key,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
        return self.get_job(record.id)

    def get_job(self, job_id: str) -> WorkflowJobRecord:
        with self.sessions() as session:
            record = session.get(WorkflowJobRecord, job_id)
            if not record:
                raise LookupError(f"任务不存在：{job_id}")
            session.expunge(record)
            return record

    def get_job_by_idempotency(
        self,
        idempotency_key: str,
    ) -> WorkflowJobRecord | None:
        with self.sessions() as session:
            record = session.scalar(
                select(WorkflowJobRecord).where(
                    WorkflowJobRecord.idempotency_key == idempotency_key
                )
            )
            if record:
                session.expunge(record)
            return record

    def record_api_write(
        self,
        *,
        idempotency_key: str,
        result: dict[str, Any],
        project_id: str | None = None,
    ) -> WorkflowJobRecord:
        existing = self.get_job_by_idempotency(idempotency_key)
        if existing:
            return existing
        now = utc_now()
        with self.sessions.begin() as session:
            record = WorkflowJobRecord(
                id=str(uuid4()),
                project_id=project_id,
                job_type=str(JobType.API_WRITE),
                status=str(JobStatus.SUCCEEDED),
                payload_json={},
                result_json=_json_ready(result),
                llm_config_id=None,
                llm_config_version=None,
                idempotency_key=idempotency_key,
                created_at=now,
                updated_at=now,
                started_at=now,
                finished_at=now,
            )
            session.add(record)
        return self.get_job(record.id)

    def get_active_job(self, project_id: str) -> WorkflowJobRecord | None:
        with self.sessions() as session:
            record = session.scalar(
                select(WorkflowJobRecord)
                .where(
                    WorkflowJobRecord.project_id == project_id,
                    WorkflowJobRecord.status.in_(
                        [str(JobStatus.QUEUED), str(JobStatus.RUNNING)]
                    ),
                )
                .order_by(WorkflowJobRecord.created_at.desc())
                .limit(1)
            )
            if record:
                session.expunge(record)
            return record

    def get_latest_project_job(
        self,
        project_id: str,
        job_type: JobType = JobType.WORKFLOW,
    ) -> WorkflowJobRecord | None:
        with self.sessions() as session:
            record = session.scalar(
                select(WorkflowJobRecord)
                .where(
                    WorkflowJobRecord.project_id == project_id,
                    WorkflowJobRecord.job_type == str(job_type),
                )
                .order_by(WorkflowJobRecord.created_at.desc())
                .limit(1)
            )
            if record:
                session.expunge(record)
            return record

    def claim_next_job(self) -> WorkflowJobRecord | None:
        with self.sessions.begin() as session:
            record = session.scalar(
                select(WorkflowJobRecord)
                .where(WorkflowJobRecord.status == str(JobStatus.QUEUED))
                .order_by(WorkflowJobRecord.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not record:
                return None
            record.status = str(JobStatus.RUNNING)
            record.started_at = utc_now()
            record.updated_at = record.started_at
            session.flush()
            session.expunge(record)
            return record

    def complete_job(
        self,
        job_id: str,
        result: dict[str, Any] | None = None,
    ) -> WorkflowJobRecord:
        with self.sessions.begin() as session:
            record = session.get(
                WorkflowJobRecord,
                job_id,
                with_for_update=True,
            )
            if not record:
                raise LookupError(f"任务不存在：{job_id}")
            record.status = str(JobStatus.SUCCEEDED)
            record.result_json = _json_ready(result or {})
            record.error_message = None
            record.finished_at = utc_now()
            record.updated_at = record.finished_at
        return self.get_job(job_id)

    def fail_job(self, job_id: str, error: str) -> WorkflowJobRecord:
        with self.sessions.begin() as session:
            record = session.get(
                WorkflowJobRecord,
                job_id,
                with_for_update=True,
            )
            if not record:
                raise LookupError(f"任务不存在：{job_id}")
            record.status = str(JobStatus.FAILED)
            record.error_message = error[:4000]
            record.finished_at = utc_now()
            record.updated_at = record.finished_at
        return self.get_job(job_id)

    def fail_interrupted_jobs(self) -> int:
        now = utc_now()
        with self.sessions.begin() as session:
            result = session.execute(
                update(WorkflowJobRecord)
                .where(WorkflowJobRecord.status == str(JobStatus.RUNNING))
                .values(
                    status=str(JobStatus.FAILED),
                    error_message="Worker重启，原运行任务状态未知，请手动重试",
                    finished_at=now,
                    updated_at=now,
                )
            )
            return int(result.rowcount or 0)

    @staticmethod
    def _has_active_job(session: Session, project_id: str) -> bool:
        return (
            session.scalar(
                select(func.count())
                .select_from(WorkflowJobRecord)
                .where(
                    WorkflowJobRecord.project_id == project_id,
                    WorkflowJobRecord.status.in_(
                        [str(JobStatus.QUEUED), str(JobStatus.RUNNING)]
                    ),
                )
            )
            or 0
        ) > 0

    def add_event(self, project_id: str, event: AuditEvent) -> None:
        with self.sessions.begin() as session:
            session.add(
                WorkflowEventRecord(
                    project_id=project_id,
                    event_type=event.event_type,
                    stage=str(event.stage),
                    message=event.message,
                    details_json=_json_ready(event.details),
                    created_at=event.created_at,
                )
            )

    def _sync_questions(self, session: Session, state: ProjectState) -> None:
        records = {
            record.question_id: record
            for record in session.scalars(
                select(QuestionRecord).where(
                    QuestionRecord.project_id == state.project_id
                )
            )
        }
        for question in state.questions:
            record = records.get(question.question_id)
            if not record:
                record = QuestionRecord(
                    project_id=state.project_id,
                    question_id=question.question_id,
                    question_type=question.question_type,
                    description=question.description,
                    importance=question.importance,
                    status=str(question.status),
                )
                session.add(record)
            record.question_type = question.question_type
            record.description = question.description
            record.importance = question.importance
            record.status = str(question.status)
            record.answer = question.answer
            record.updated_at = utc_now()

    def _sync_logic_issues(self, session: Session, state: ProjectState) -> None:
        records = {
            record.issue_id: record
            for record in session.scalars(
                select(LogicIssueRecord).where(
                    LogicIssueRecord.project_id == state.project_id
                )
            )
        }
        for issue in state.logic_issues:
            record = records.get(issue.issue_id)
            if not record:
                record = LogicIssueRecord(
                    project_id=state.project_id,
                    issue_id=issue.issue_id,
                    dimension=issue.dimension,
                    description=issue.description,
                    severity=str(issue.severity),
                    status=str(issue.status),
                )
                session.add(record)
            record.dimension = issue.dimension
            record.description = issue.description
            record.severity = str(issue.severity)
            record.status = str(issue.status)
            record.resolution = issue.resolution
            record.updated_at = utc_now()

    def _sync_approvals(self, session: Session, state: ProjectState) -> None:
        approval_ids = [approval.approval_id for approval in state.approvals]
        stale_query = delete(ApprovalRecord).where(
            ApprovalRecord.project_id == state.project_id
        )
        if approval_ids:
            stale_query = stale_query.where(
                ApprovalRecord.approval_id.not_in(approval_ids)
            )
        session.execute(stale_query)
        existing = set(
            session.scalars(
                select(ApprovalRecord.approval_id).where(
                    ApprovalRecord.project_id == state.project_id
                )
            )
        )
        for approval in state.approvals:
            if approval.approval_id in existing:
                continue
            session.add(
                ApprovalRecord(
                    approval_id=approval.approval_id,
                    project_id=state.project_id,
                    kind=approval.kind,
                    stage=str(approval.stage),
                    artifact_version=approval.artifact_version,
                    approved_at=approval.approved_at,
                )
            )
