from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.engine import make_url

from prd_agent.flow import rollback_targets_for
from prd_agent.gates import (
    WorkflowGateError,
    assert_logic_ready,
    assert_structure_ready,
    logic_readiness_errors,
    structure_readiness_errors,
)
from prd_agent.models import (
    ArtifactType,
    ItemStatus,
    JobStatus,
    JobType,
    ProjectState,
    Severity,
    Stage,
    StageStatus,
)
from prd_agent.repositories import (
    ActiveJobError,
    ArtifactNotFoundError,
    LlmConfigNotFoundError,
    LlmConfigRecord,
    ProjectNotFoundError,
    SQLAlchemyRepository,
    WorkflowJobRecord,
)
from prd_agent.services import (
    ensure_default_llm_config,
    workflow_for_config,
)
from prd_agent.settings import Settings, get_settings, validate_database_pair


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class ProjectCreate(ApiModel):
    requirement: str = Field(min_length=1)
    llm_config_id: str | None = Field(default=None, alias="llmConfigId")


class AnswerInput(ApiModel):
    item_id: str = Field(alias="itemId")
    answer: str = Field(min_length=1)


class AnswersRequest(ApiModel):
    answers: list[AnswerInput] = Field(min_length=1)


class FeedbackRequest(ApiModel):
    feedback: str = Field(min_length=1)


class RollbackRequest(ApiModel):
    target_stage: Stage = Field(alias="targetStage")
    feedback: str | None = None


class PrdReviewOverrideRequest(ApiModel):
    reason: str = Field(min_length=1)


class ArchiveRequest(ApiModel):
    archived: bool


class WaiveRequest(ApiModel):
    reason: str = Field(min_length=1)


class ProjectConfigRequest(ApiModel):
    llm_config_id: str = Field(alias="llmConfigId")


class LlmConfigInput(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=255)
    api_key: str | None = Field(default=None, alias="apiKey")
    clear_api_key: bool = Field(default=False, alias="clearApiKey")
    base_url: str | None = Field(default=None, alias="baseUrl")
    temperature: float = Field(default=0.2, ge=0, le=2)
    timeout_seconds: int = Field(default=120, ge=1, le=600, alias="timeoutSeconds")
    native_structured_output: bool | None = Field(
        default=None,
        alias="nativeStructuredOutput",
    )
    make_default: bool = Field(default=False, alias="makeDefault")
    archived: bool = False


class DatabaseSetupRequest(ApiModel):
    database_url: str = Field(min_length=1, alias="databaseUrl")
    test_database_url: str = Field(min_length=1, alias="testDatabaseUrl")


IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=120),
]


def create_app(
    settings: Settings | None = None,
    repository: SQLAlchemyRepository | None = None,
) -> FastAPI:
    configured = settings or get_settings()
    setup_error: str | None = None
    repo = repository
    if repo is None and configured.database_url and configured.test_database_url:
        try:
            repo = SQLAlchemyRepository.from_url(
                configured.database_url,
                connect_timeout=configured.database_connect_timeout_seconds,
                read_timeout=configured.database_read_timeout_seconds,
            )
            _test_database_connection(repo)
        except Exception as exc:
            setup_error = str(exc)
            repo = None
    elif repo is None:
        setup_error = "缺少 DATABASE_URL 或 TEST_DATABASE_URL"

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if repo is not None:
            ensure_default_llm_config(repo, configured)
        yield

    app = FastAPI(
        title="PRD Agent API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.settings = configured
    app.state.repository = repo
    app.state.setup_error = setup_error
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _register_exception_handlers(app)
    _register_setup_routes(app, configured, repo is not None, setup_error)
    if repo is not None:
        _register_routes(app, repo, configured)
    else:
        _register_setup_required_routes(app)
    _mount_web(app, configured.project_root / "web" / "dist")
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    handled = (
        ActiveJobError,
        ArtifactNotFoundError,
        LlmConfigNotFoundError,
        ProjectNotFoundError,
        WorkflowGateError,
        ValueError,
        LookupError,
    )

    async def handle_exception(_: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, ActiveJobError):
            return _error("active_job", str(exc), 409)
        if isinstance(exc, handled):
            status = 404 if isinstance(
                exc,
                (
                    ArtifactNotFoundError,
                    LlmConfigNotFoundError,
                    ProjectNotFoundError,
                    LookupError,
                ),
            ) else 400
            details: dict[str, Any] = {}
            if isinstance(exc, WorkflowGateError):
                details["reasons"] = exc.errors
            return _error("request_rejected", str(exc), status, details)
        return _error("internal_error", "服务内部错误", 500)

    for exception_type in handled:
        app.add_exception_handler(exception_type, handle_exception)
    app.add_exception_handler(Exception, handle_exception)


def _register_setup_routes(
    app: FastAPI,
    settings: Settings,
    ready: bool,
    setup_error: str | None,
) -> None:
    prefix = "/api/v1"

    @app.get(f"{prefix}/health")
    def health() -> dict[str, Any]:
        return _ok({"status": "ok", "setupRequired": not ready})

    @app.get(f"{prefix}/setup/status")
    def setup_status() -> dict[str, Any]:
        configured = bool(settings.database_url and settings.test_database_url)
        return _ok(
            {
                "ready": ready,
                "setupRequired": not ready,
                "databaseConfigured": configured,
                "databaseUrl": _mask_database_url(settings.database_url),
                "testDatabaseUrl": _mask_database_url(settings.test_database_url),
                "error": setup_error,
            }
        )

    @app.post(f"{prefix}/setup/database/test")
    def test_database_setup(body: DatabaseSetupRequest) -> dict[str, Any]:
        database_url, test_database_url = _validated_setup_urls(body)
        _test_database_url(
            database_url,
            settings.database_connect_timeout_seconds,
            settings.database_read_timeout_seconds,
        )
        _test_database_url(
            test_database_url,
            settings.database_connect_timeout_seconds,
            settings.database_read_timeout_seconds,
        )
        return _ok(
            {
                "ok": True,
                "databaseUrl": _mask_database_url(database_url),
                "testDatabaseUrl": _mask_database_url(test_database_url),
            }
        )

    @app.post(f"{prefix}/setup/database/save")
    def save_database_setup(body: DatabaseSetupRequest) -> dict[str, Any]:
        database_url, test_database_url = _validated_setup_urls(body)
        _test_database_url(
            database_url,
            settings.database_connect_timeout_seconds,
            settings.database_read_timeout_seconds,
        )
        _test_database_url(
            test_database_url,
            settings.database_connect_timeout_seconds,
            settings.database_read_timeout_seconds,
        )
        env_path = settings.project_root / ".env"
        _upsert_env_file(
            env_path,
            {
                "DATABASE_URL": database_url,
                "TEST_DATABASE_URL": test_database_url,
            },
        )
        return _ok(
            {
                "saved": True,
                "restartRequired": True,
                "envPath": str(env_path),
                "databaseUrl": _mask_database_url(database_url),
                "testDatabaseUrl": _mask_database_url(test_database_url),
            }
        )


def _register_setup_required_routes(app: FastAPI) -> None:
    prefix = "/api/v1"

    @app.api_route(
        f"{prefix}/{{path:path}}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )
    def setup_required(path: str) -> JSONResponse:
        return _error(
            "setup_required",
            "请先完成数据库配置并重启 API/Worker",
            503,
            {"path": f"{prefix}/{path}"},
        )


def _register_routes(
    app: FastAPI,
    repo: SQLAlchemyRepository,
    settings: Settings,
) -> None:
    prefix = "/api/v1"

    @app.post(f"{prefix}/projects", status_code=202)
    def create_project(
        body: ProjectCreate,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        existing = repo.get_job_by_idempotency(idempotency_key)
        if existing:
            return _ok(existing.result_json or _job_data(existing), "accepted")
        config = (
            repo.get_llm_config(body.llm_config_id)
            if body.llm_config_id
            else ensure_default_llm_config(repo, settings)
        )
        if not config:
            raise LlmConfigNotFoundError(
                "尚未配置默认LLM，请先在设置页创建配置"
            )
        engine = workflow_for_config(repo, settings, config)
        state = engine.initialize_project(body.requirement, config.id)
        job = repo.enqueue_job(
            job_type=JobType.WORKFLOW,
            idempotency_key=idempotency_key,
            payload={"operation": "advance"},
            project_id=state.project_id,
            llm_config_id=config.id,
            llm_config_version=config.version,
        )
        return _ok(
            {"projectId": state.project_id, "jobId": job.id},
            "accepted",
        )

    @app.get(f"{prefix}/projects")
    def list_projects(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
        search: str = "",
        archived: bool = False,
    ) -> dict[str, Any]:
        records, total = repo.list_projects(page, page_size, search, archived)
        return _ok(
            {
                "items": [_project_summary(record) for record in records],
                "page": page,
                "pageSize": page_size,
                "total": total,
            }
        )

    @app.get(f"{prefix}/projects/{{project_id}}")
    def get_project(project_id: str) -> dict[str, Any]:
        return _ok(_project_detail(repo, project_id))

    @app.post(f"{prefix}/projects/{{project_id}}/answers", status_code=202)
    def submit_answers(
        project_id: str,
        body: AnswersRequest,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        state = repo.get_project(project_id)
        answers = {item.item_id: item.answer.strip() for item in body.answers}
        required = _required_answer_ids(state)
        missing = sorted(required - answers.keys())
        if missing:
            raise ValueError(f"以下问题尚未回答：{', '.join(missing)}")
        unknown = sorted(answers.keys() - _open_item_ids(state))
        if unknown:
            raise ValueError(f"问题不存在或已关闭：{', '.join(unknown)}")
        text = "\n".join(f"{key}：{answers[key]}" for key in sorted(answers))
        job = _enqueue_project_job(
            repo,
            project_id,
            idempotency_key,
            {"operation": "input", "input": text},
        )
        return _ok(_job_data(job), "accepted")

    @app.post(f"{prefix}/projects/{{project_id}}/feedback", status_code=202)
    def submit_feedback(
        project_id: str,
        body: FeedbackRequest,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        job = _enqueue_project_job(
            repo,
            project_id,
            idempotency_key,
            {"operation": "input", "input": body.feedback.strip()},
        )
        return _ok(_job_data(job), "accepted")

    @app.post(f"{prefix}/projects/{{project_id}}/advance", status_code=202)
    def advance_project(
        project_id: str,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        if repo.get_active_job(project_id):
            raise ActiveJobError("项目有运行中任务，请等待完成")
        _assert_advance_allowed(repo.get_project(project_id))
        job = _enqueue_project_job(
            repo,
            project_id,
            idempotency_key,
            {"operation": "input", "input": "下一步"},
        )
        return _ok(_job_data(job), "accepted")

    @app.post(f"{prefix}/projects/{{project_id}}/retry", status_code=202)
    def retry_project(
        project_id: str,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        job = _enqueue_project_job(
            repo,
            project_id,
            idempotency_key,
            {"operation": "input", "input": "重试"},
        )
        return _ok(_job_data(job), "accepted")

    @app.post(f"{prefix}/projects/{{project_id}}/rollback", status_code=202)
    def rollback_project(
        project_id: str,
        body: RollbackRequest,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        record = repo.get_project_record(project_id)
        if record.archived_at:
            raise WorkflowGateError(["归档项目不能回退"])
        state = ProjectState.model_validate(record.state_json)
        targets = {target["stage"] for target in _rollback_targets(state)}
        if str(body.target_stage) not in targets:
            raise WorkflowGateError(["当前阶段不支持回退到该目标"])
        job = _enqueue_project_job(
            repo,
            project_id,
            idempotency_key,
            {
                "operation": "rollback",
                "targetStage": str(body.target_stage),
                "feedback": (body.feedback or "").strip(),
            },
        )
        return _ok(_job_data(job), "accepted")

    @app.post(
        f"{prefix}/projects/{{project_id}}/prd-review/override",
        status_code=202,
    )
    def override_prd_review(
        project_id: str,
        body: PrdReviewOverrideRequest,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        reason = body.reason.strip()
        if not reason:
            raise WorkflowGateError(["强行同意必须填写理由"])
        record = repo.get_project_record(project_id)
        if record.archived_at:
            raise WorkflowGateError(["归档项目不能强行同意终审"])
        state = ProjectState.model_validate(record.state_json)
        if "overrideReview" not in _allowed_actions(state, None, None):
            raise WorkflowGateError(["当前阶段不支持强行同意终审"])
        job = _enqueue_project_job(
            repo,
            project_id,
            idempotency_key,
            {
                "operation": "overridePrdReview",
                "reason": reason,
            },
        )
        return _ok(_job_data(job), "accepted")

    @app.post(
        f"{prefix}/projects/{{project_id}}/sdd/regenerate",
        status_code=202,
    )
    def regenerate_sdd(
        project_id: str,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        record = repo.get_project_record(project_id)
        if record.archived_at:
            raise WorkflowGateError(["归档项目不能重新生成SDD"])
        state = ProjectState.model_validate(record.state_json)
        if "regenerateSdd" not in _allowed_actions(state, None, None):
            raise WorkflowGateError(["当前项目不能重新生成SDD"])
        job = _enqueue_project_job(
            repo,
            project_id,
            idempotency_key,
            {"operation": "regenerateSdd"},
        )
        return _ok(_job_data(job), "accepted")

    @app.post(
        f"{prefix}/projects/{{project_id}}/logic-issues/{{issue_id}}/waive"
    )
    def waive_logic_issue(
        project_id: str,
        issue_id: str,
        body: WaiveRequest,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        repeated = _idempotent_result(repo, idempotency_key)
        if repeated:
            return _ok(repeated)
        config = _project_config(repo, project_id)
        state = workflow_for_config(repo, settings, config).submit_user_input(
            project_id,
            f"豁免 {issue_id}: {body.reason.strip()}",
        )
        result = {"projectId": state.project_id, "issueId": issue_id}
        repo.record_api_write(
            idempotency_key=idempotency_key,
            result=result,
            project_id=project_id,
        )
        return _ok(result)

    @app.post(f"{prefix}/projects/{{project_id}}/archive")
    def archive_project(
        project_id: str,
        body: ArchiveRequest,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        repeated = _idempotent_result(repo, idempotency_key)
        if repeated:
            return _ok(repeated)
        record = repo.archive_project(project_id, body.archived)
        result = {
            "projectId": record.id,
            "archived": record.archived_at is not None,
        }
        repo.record_api_write(
            idempotency_key=idempotency_key,
            result=result,
            project_id=project_id,
        )
        return _ok(result)

    @app.put(f"{prefix}/projects/{{project_id}}/llm-config")
    def change_project_config(
        project_id: str,
        body: ProjectConfigRequest,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        repeated = _idempotent_result(repo, idempotency_key)
        if repeated:
            return _ok(repeated)
        repo.set_project_llm_config(project_id, body.llm_config_id)
        result = {
            "projectId": project_id,
            "llmConfigId": body.llm_config_id,
        }
        repo.record_api_write(
            idempotency_key=idempotency_key,
            result=result,
            project_id=project_id,
        )
        return _ok(result)

    @app.get(f"{prefix}/jobs/{{job_id}}")
    def get_job(job_id: str) -> dict[str, Any]:
        return _ok(_job_data(repo.get_job(job_id)))

    @app.get(f"{prefix}/projects/{{project_id}}/artifacts")
    def list_artifacts(project_id: str) -> dict[str, Any]:
        repo.get_project(project_id)
        return _ok(
            {"items": [_artifact_data(item, include_content=False) for item in repo.list_artifacts(project_id)]}
        )

    @app.get(
        f"{prefix}/projects/{{project_id}}/artifacts/{{artifact_type}}/{{version}}"
    )
    def get_artifact(
        project_id: str,
        artifact_type: ArtifactType,
        version: int,
    ) -> dict[str, Any]:
        record = repo.get_artifact(project_id, artifact_type, version)
        return _ok(_artifact_data(record, include_content=True))

    @app.get(
        f"{prefix}/projects/{{project_id}}/artifacts/"
        "{artifact_type}/{version}/download"
    )
    def download_artifact(
        project_id: str,
        artifact_type: ArtifactType,
        version: int,
    ) -> PlainTextResponse:
        record = repo.get_artifact(project_id, artifact_type, version)
        filename = f"{artifact_type.value}-v{version}.md"
        return PlainTextResponse(
            record.content,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )

    @app.get(f"{prefix}/llm-configs")
    def list_llm_configs(include_archived: bool = False) -> dict[str, Any]:
        return _ok(
            {
                "items": [
                    _llm_config_data(item)
                    for item in repo.list_llm_configs(include_archived)
                ]
            }
        )

    @app.post(f"{prefix}/llm-configs")
    def create_llm_config(
        body: LlmConfigInput,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        repeated = _idempotent_result(repo, idempotency_key)
        if repeated:
            return _ok(repeated)
        record = repo.create_llm_config(
            name=body.name.strip(),
            provider=body.provider.strip(),
            model=body.model.strip(),
            api_key=body.api_key.strip() if body.api_key else None,
            base_url=body.base_url.strip() if body.base_url else None,
            temperature=body.temperature,
            timeout_seconds=body.timeout_seconds,
            native_structured_output=body.native_structured_output,
            make_default=body.make_default,
        )
        result = _llm_config_data(record)
        repo.record_api_write(idempotency_key=idempotency_key, result=result)
        return _ok(result)

    @app.put(f"{prefix}/llm-configs/{{config_id}}")
    def update_llm_config(
        config_id: str,
        body: LlmConfigInput,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        repeated = _idempotent_result(repo, idempotency_key)
        if repeated:
            return _ok(repeated)
        update_key = body.clear_api_key or body.api_key is not None
        record = repo.update_llm_config(
            config_id,
            name=body.name.strip(),
            provider=body.provider.strip(),
            model=body.model.strip(),
            api_key=(
                None
                if body.clear_api_key
                else body.api_key.strip() if body.api_key else None
            ),
            update_api_key=update_key,
            base_url=body.base_url.strip() if body.base_url else None,
            temperature=body.temperature,
            timeout_seconds=body.timeout_seconds,
            native_structured_output=body.native_structured_output,
            make_default=body.make_default,
            archived=body.archived,
        )
        result = _llm_config_data(record)
        repo.record_api_write(idempotency_key=idempotency_key, result=result)
        return _ok(result)

    @app.post(f"{prefix}/llm-configs/{{config_id}}/test", status_code=202)
    def test_llm_config(
        config_id: str,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        config = repo.get_llm_config(config_id)
        job = repo.enqueue_job(
            job_type=JobType.LLM_TEST,
            idempotency_key=idempotency_key,
            payload={},
            llm_config_id=config.id,
            llm_config_version=config.version,
        )
        return _ok(_job_data(job), "accepted")


def _enqueue_project_job(
    repo: SQLAlchemyRepository,
    project_id: str,
    idempotency_key: str,
    payload: dict[str, Any],
) -> WorkflowJobRecord:
    existing = repo.get_job_by_idempotency(idempotency_key)
    if existing:
        return existing
    config = _project_config(repo, project_id)
    return repo.enqueue_job(
        job_type=JobType.WORKFLOW,
        idempotency_key=idempotency_key,
        payload=payload,
        project_id=project_id,
        llm_config_id=config.id,
        llm_config_version=config.version,
    )


def _project_config(
    repo: SQLAlchemyRepository,
    project_id: str,
) -> LlmConfigRecord:
    record = repo.get_project_record(project_id)
    if not record.llm_config_id:
        raise LlmConfigNotFoundError("项目尚未绑定LLM配置")
    return repo.get_llm_config(record.llm_config_id)


def _project_detail(
    repo: SQLAlchemyRepository,
    project_id: str,
) -> dict[str, Any]:
    record = repo.get_project_record(project_id)
    state = ProjectState.model_validate(record.state_json)
    active_job = repo.get_active_job(project_id)
    latest_job = repo.get_latest_project_job(project_id)
    artifacts = repo.list_artifacts(project_id)
    config = (
        repo.get_llm_config(record.llm_config_id)
        if record.llm_config_id
        else None
    )
    return {
        **state.model_dump(mode="json", by_alias=True),
        "archivedAt": record.archived_at,
        "llmConfig": _llm_config_data(config) if config else None,
        "activeJob": _job_data(active_job) if active_job else None,
        "lastJob": _job_data(latest_job) if latest_job else None,
        "artifacts": [
            _artifact_data(item, include_content=False) for item in artifacts
        ],
        "gateErrors": _gate_errors(state),
        "allowedActions": _allowed_actions(state, active_job, record.archived_at),
        "rollbackTargets": (
            []
            if active_job or record.archived_at
            else _rollback_targets(state)
        ),
    }


def _project_summary(record: Any) -> dict[str, Any]:
    state = ProjectState.model_validate(record.state_json)
    return {
        "projectId": record.id,
        "title": state.requirement_spec.title or "未命名项目",
        "summary": state.requirement_spec.summary,
        "stage": str(state.stage),
        "stageStatus": str(state.stage_status),
        "roundNumber": state.round_number,
        "archivedAt": record.archived_at,
        "updatedAt": record.updated_at,
    }


def _required_answer_ids(state: ProjectState) -> set[str]:
    if state.stage == Stage.STRUCTURING:
        return {
            item.question_id
            for item in state.questions
            if item.status == ItemStatus.OPEN
        }
    if state.stage == Stage.LOGIC_VALIDATING:
        return {
            item.issue_id
            for item in state.logic_issues
            if item.status == ItemStatus.OPEN
            and item.severity in {Severity.BLOCKING, Severity.IMPORTANT}
        }
    raise ValueError("当前阶段不接受批量回答")


def _assert_advance_allowed(state: ProjectState) -> None:
    if state.stage_status != StageStatus.WAITING_USER:
        raise WorkflowGateError(["当前阶段不接受下一步确认"])
    if state.stage == Stage.STRUCTURING:
        assert_structure_ready(state)
        return
    if state.stage == Stage.LOGIC_VALIDATING:
        assert_logic_ready(state)
        return
    if state.stage == Stage.PRD_TYPE_CONFIRMING:
        if not state.product_type:
            raise WorkflowGateError(["尚未生成产品类型识别结果"])
        return
    if state.stage == Stage.SDD_CONFIRMING:
        return
    raise WorkflowGateError([f"阶段 {state.stage} 不接受下一步确认"])


def _gate_errors(state: ProjectState) -> list[str]:
    if state.stage_status != StageStatus.WAITING_USER:
        return []
    if state.stage == Stage.STRUCTURING:
        return structure_readiness_errors(state)
    if state.stage == Stage.LOGIC_VALIDATING:
        return logic_readiness_errors(state)
    try:
        _assert_advance_allowed(state)
    except WorkflowGateError as exc:
        return exc.errors
    return []


def _open_item_ids(state: ProjectState) -> set[str]:
    return {
        item.question_id
        for item in state.questions
        if item.status == ItemStatus.OPEN
    } | {
        item.issue_id
        for item in state.logic_issues
        if item.status == ItemStatus.OPEN
    }


def _allowed_actions(
    state: ProjectState,
    active_job: WorkflowJobRecord | None,
    archived_at: Any,
) -> list[str]:
    if active_job or archived_at:
        return []
    if state.stage_status == "failed":
        actions = ["retry"]
        if state.stage == Stage.PRD_REVIEWING:
            actions.append("feedback")
            actions.append("overrideReview")
        if _rollback_targets(state):
            actions.append("rollback")
        return actions
    actions: list[str] = []
    if state.stage in {Stage.STRUCTURING, Stage.LOGIC_VALIDATING}:
        actions.append("answer")
        actions.append("feedback")
    try:
        _assert_advance_allowed(state)
    except WorkflowGateError:
        pass
    else:
        actions.append("advance")
    if state.stage == Stage.PRD_TYPE_CONFIRMING:
        actions.append("feedback")
    if (
        state.stage == Stage.COMPLETED
        and state.stage_status == "completed"
        and "sdd" in state.artifact_versions
    ):
        actions.append("regenerateSdd")
    if _rollback_targets(state):
        actions.append("rollback")
    return actions


def _rollback_targets(state: ProjectState) -> list[dict[str, str]]:
    labels = {
        Stage.LOGIC_VALIDATING: "回到逻辑校验",
        Stage.PRD_TYPE_CONFIRMING: "回到产品类型确认",
        Stage.PRD_REVISING: "回到PRD修订",
    }
    descriptions = {
        Stage.LOGIC_VALIDATING: "把终审阻断问题纳入需求逻辑后重新执行7维扫描",
        Stage.PRD_TYPE_CONFIRMING: "重新识别产品类型并重新生成PRD",
        Stage.PRD_REVISING: "基于当前PRD和终审报告生成新版PRD",
    }
    return [
        {
            "stage": str(stage),
            "label": labels[stage],
            "description": descriptions[stage],
        }
        for stage in rollback_targets_for(state.stage)
    ]


def _llm_config_data(record: LlmConfigRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "name": record.name,
        "provider": record.provider,
        "model": record.model,
        "baseUrl": record.base_url,
        "temperature": record.temperature,
        "timeoutSeconds": record.timeout_seconds,
        "nativeStructuredOutput": record.native_structured_output,
        "version": record.version,
        "isDefault": record.is_default,
        "archivedAt": record.archived_at,
        "hasApiKey": bool(record.api_key),
        "apiKeyMask": _mask_key(record.api_key),
        "createdAt": record.created_at,
        "updatedAt": record.updated_at,
    }


def _mask_key(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:3]}{'*' * 8}{value[-4:]}"


def _job_data(record: WorkflowJobRecord | None) -> dict[str, Any] | None:
    if not record:
        return None
    return {
        "jobId": record.id,
        "projectId": record.project_id,
        "jobType": record.job_type,
        "status": record.status,
        "result": record.result_json,
        "errorMessage": record.error_message,
        "createdAt": record.created_at,
        "updatedAt": record.updated_at,
        "startedAt": record.started_at,
        "finishedAt": record.finished_at,
    }


def _artifact_data(record: Any, *, include_content: bool) -> dict[str, Any]:
    data = {
        "artifactType": record.artifact_type,
        "version": record.version,
        "metadata": record.metadata_json,
        "createdAt": record.created_at,
    }
    if include_content:
        data["content"] = record.content
    return data


def _idempotent_result(
    repo: SQLAlchemyRepository,
    idempotency_key: str,
) -> dict[str, Any] | None:
    existing = repo.get_job_by_idempotency(idempotency_key)
    return existing.result_json if existing else None


def _validated_setup_urls(body: DatabaseSetupRequest) -> tuple[str, str]:
    database_url = body.database_url.strip()
    test_database_url = body.test_database_url.strip()
    validate_database_pair(database_url, test_database_url)
    return database_url, test_database_url


def _test_database_url(
    database_url: str,
    connect_timeout: int,
    read_timeout: int,
) -> None:
    repo = SQLAlchemyRepository.from_url(
        database_url,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
    )
    try:
        _test_database_connection(repo)
    except Exception as exc:
        raise ValueError(f"数据库连接失败：{exc}") from exc
    finally:
        repo.engine.dispose()


def _test_database_connection(repo: SQLAlchemyRepository) -> None:
    with repo.engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def _mask_database_url(value: str | None) -> str | None:
    if not value:
        return None
    return make_url(value).render_as_string(hide_password=True)


def _upsert_env_file(path: Path, updates: dict[str, str]) -> None:
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    output: list[str] = []
    for line in existing:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def _ok(data: Any, message: str = "ok") -> dict[str, Any]:
    return {"code": "success", "data": data, "message": message}


def _error(
    code: str,
    message: str,
    status: int,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "code": code,
            "message": message,
            "details": details or {},
        },
    )


def _mount_web(app: FastAPI, dist: Path) -> None:
    if not dist.exists():
        return
    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        requested = dist / full_path
        if full_path and requested.is_file():
            return FileResponse(requested)
        return FileResponse(dist / "index.html")
