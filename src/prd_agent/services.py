from __future__ import annotations

from typing import Any

from prd_agent.attachments import (
    extract_attachment_text,
    format_attachment_source,
)
from prd_agent.agents import AgentFactory
from prd_agent.flow import WorkflowEngine
from prd_agent.gates import WorkflowGateError
from prd_agent.models import JobType, SourceInput, Stage, StageStatus
from prd_agent.repositories import (
    LlmConfigNotFoundError,
    LlmConfigRecord,
    SQLAlchemyRepository,
    WorkflowJobRecord,
)
from prd_agent.settings import Settings
from prd_agent.tasks import CrewAITaskExecutor


def ensure_default_llm_config(
    repository: SQLAlchemyRepository,
    settings: Settings,
) -> LlmConfigRecord | None:
    existing = repository.get_default_llm_config()
    if existing:
        return existing
    if not settings.resolved_llm_model:
        return None
    settings.require_llm()
    return repository.create_llm_config(
        name="环境默认",
        provider=settings.llm_provider or _provider_from_model(
            settings.resolved_llm_model or ""
        ),
        model=settings.resolved_llm_model or "",
        api_key=settings.resolved_llm_api_key,
        base_url=settings.llm_base_url,
        temperature=settings.llm_temperature,
        timeout_seconds=settings.llm_timeout_seconds,
        native_structured_output=settings.llm_native_structured_output,
        make_default=True,
    )


def settings_for_config(
    settings: Settings,
    config: LlmConfigRecord,
) -> Settings:
    return settings.model_copy(
        update={
            "llm_model": config.model,
            "llm_provider": config.provider,
            "llm_api_key": config.api_key,
            "llm_base_url": config.base_url,
            "llm_temperature": config.temperature,
            "llm_timeout_seconds": config.timeout_seconds,
            "llm_native_structured_output": config.native_structured_output,
            "openai_model": None,
            "openai_api_key": None,
        }
    )


def workflow_for_config(
    repository: SQLAlchemyRepository,
    settings: Settings,
    config: LlmConfigRecord,
    agent_factory: AgentFactory | None = None,
) -> WorkflowEngine:
    configured = settings_for_config(settings, config)
    agents = agent_factory or AgentFactory(configured)
    return WorkflowEngine(
        repository=repository,
        executor=CrewAITaskExecutor(agents),
        max_prd_revision_rounds=settings.max_prd_revision_rounds,
        artifact_metadata={
            "llmProvider": config.provider,
            "llmModel": config.model,
            "llmConfigId": config.id,
            "llmConfigVersion": config.version,
        },
    )


class JobRunner:
    def __init__(
        self,
        repository: SQLAlchemyRepository,
        settings: Settings,
    ):
        self.repository = repository
        self.settings = settings

    def run(self, job: WorkflowJobRecord) -> dict[str, Any]:
        config = self._load_versioned_config(job)
        if job.job_type == str(JobType.LLM_TEST):
            configured = settings_for_config(self.settings, config)
            response = AgentFactory(configured).llm.call(
                "只返回英文大写 OK，不要输出其他内容。"
            )
            return {"response": str(response).strip()[:200]}
        if job.job_type != str(JobType.WORKFLOW):
            raise ValueError(f"不支持的任务类型：{job.job_type}")
        if not job.project_id:
            raise ValueError("工作流任务缺少projectId")

        attachments = self.repository.list_project_attachments(job.project_id)
        agent_factory = None
        if attachments:
            configured = settings_for_config(self.settings, config)
            agent_factory = AgentFactory(configured)
            self._process_project_attachments(
                job.project_id,
                agent_factory.llm,
                attachments,
            )
        engine = workflow_for_config(
            self.repository,
            self.settings,
            config,
            agent_factory,
        )
        operation = job.payload_json.get("operation")
        try:
            if operation == "advance":
                state = engine.advance(job.project_id)
            elif operation == "input":
                user_input = str(job.payload_json.get("input", "")).strip()
                if not user_input:
                    raise ValueError("工作流任务缺少用户输入")
                state = engine.submit_user_input(job.project_id, user_input)
            elif operation == "rollback":
                target_stage = str(job.payload_json.get("targetStage", "")).strip()
                if not target_stage:
                    raise ValueError("工作流回退任务缺少目标阶段")
                feedback = str(job.payload_json.get("feedback", "")).strip()
                state = engine.rollback(
                    job.project_id,
                    Stage(target_stage),
                    feedback or None,
                )
            elif operation == "overridePrdReview":
                reason = str(job.payload_json.get("reason", "")).strip()
                if not reason:
                    raise ValueError("强行同意PRD终审必须填写理由")
                state = engine.override_prd_review(job.project_id, reason)
            elif operation == "regenerateSdd":
                state = engine.regenerate_sdd(job.project_id)
            else:
                raise ValueError(f"不支持的工作流操作：{operation}")
        except WorkflowGateError as exc:
            state = self.repository.get_project(job.project_id)
            return {
                "projectId": state.project_id,
                "stage": str(state.stage),
                "stageStatus": str(state.stage_status),
                "gateErrors": exc.errors,
            }
        return {
            "projectId": state.project_id,
            "stage": str(state.stage),
            "stageStatus": str(state.stage_status),
        }

    def _process_project_attachments(
        self,
        project_id: str,
        llm: Any,
        attachments: list[Any],
    ) -> None:
        for attachment in attachments:
            if attachment.status not in {"pending", "failed"}:
                continue
            try:
                extracted_text = extract_attachment_text(
                    attachment,
                    self.settings.resolved_upload_dir,
                    llm if attachment.kind == "image" else None,
                )
                self.repository.update_project_attachment(
                    attachment.id,
                    status="processed",
                    extracted_text=extracted_text,
                    error_message=None,
                )
            except Exception as exc:
                self.repository.update_project_attachment(
                    attachment.id,
                    status="failed",
                    extracted_text=None,
                    error_message=str(exc),
                )
                state = self.repository.get_project(project_id)
                state.stage_status = StageStatus.FAILED
                self.repository.save_project(state)
                raise ValueError(
                    f"附件处理失败：{attachment.original_filename}：{exc}"
                ) from exc

        refreshed = self.repository.list_project_attachments(project_id)
        processed = [
            item
            for item in refreshed
            if item.status == "processed" and item.extracted_text
        ]
        if not processed:
            return

        state = self.repository.get_project(project_id)
        existing_attachment_ids = {
            source.attachment_id
            for source in state.requirement_spec.source_inputs
            if source.attachment_id
        }
        appended = False
        for attachment in processed:
            if attachment.id in existing_attachment_ids:
                continue
            state.requirement_spec.source_inputs.append(
                SourceInput(
                    text=format_attachment_source(
                        attachment,
                        attachment.extracted_text or "",
                    ),
                    source_type=attachment.kind,
                    filename=attachment.original_filename,
                    attachment_id=attachment.id,
                )
            )
            appended = True
        if appended:
            self.repository.save_project(state)

    def _load_versioned_config(
        self,
        job: WorkflowJobRecord,
    ) -> LlmConfigRecord:
        if not job.llm_config_id:
            raise LlmConfigNotFoundError("任务缺少LLM配置")
        config = self.repository.get_llm_config(job.llm_config_id)
        if config.archived_at:
            raise ValueError("任务使用的LLM配置已归档")
        if config.version != job.llm_config_version:
            raise ValueError("LLM配置在任务排队后发生变化，请重新提交")
        return config


def _provider_from_model(model: str) -> str:
    if "/" not in model:
        return "openai"
    return model.split("/", maxsplit=1)[0]
