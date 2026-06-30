from __future__ import annotations

from types import SimpleNamespace
from typing import Never

import pytest

from prd_agent.gates import WorkflowGateError
from prd_agent.models import JobType, ProjectState, Stage, StageStatus
from prd_agent.services import JobRunner, ensure_default_llm_config
from prd_agent.settings import Settings


class EmptyConfigRepository:
    def get_default_llm_config(self) -> None:
        return None

    def create_llm_config(self, **_: object) -> Never:
        raise AssertionError("没有环境模型时不应创建默认配置")


def test_missing_environment_model_allows_web_first_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "LLM_MODEL",
        "LLM_API_KEY",
        "LLM_PROVIDER",
        "OPENAI_MODEL",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(
        _env_file=None,
        database_url=(
            "mysql+pymysql://user:password@localhost:3306/"
            "prd_agent?charset=utf8mb4"
        ),
        test_database_url=(
            "mysql+pymysql://user:password@localhost:3306/"
            "prd_agent_test?charset=utf8mb4"
        ),
    )

    result = ensure_default_llm_config(EmptyConfigRepository(), settings)  # type: ignore[arg-type]

    assert result is None


def test_job_runner_returns_gate_errors_without_failing_job(monkeypatch) -> None:
    state = ProjectState(
        project_id="project-1",
        stage=Stage.STRUCTURING,
        stage_status=StageStatus.WAITING_USER,
    )

    class Repository:
        def list_project_attachments(self, project_id: str) -> list[object]:
            assert project_id == "project-1"
            return []

        def get_llm_config(self, config_id: str):
            return SimpleNamespace(id=config_id, version=1, archived_at=None)

        def get_project(self, project_id: str) -> ProjectState:
            assert project_id == "project-1"
            return state

    class Engine:
        def submit_user_input(self, project_id: str, user_input: str) -> ProjectState:
            assert project_id == "project-1"
            assert user_input == "下一步"
            raise WorkflowGateError(["交互逻辑尚未明确", "操作影响尚不可追溯"])

    monkeypatch.setattr(
        "prd_agent.services.workflow_for_config",
        lambda *_: Engine(),
    )
    job = SimpleNamespace(
        job_type=str(JobType.WORKFLOW),
        project_id="project-1",
        payload_json={"operation": "input", "input": "下一步"},
        llm_config_id="config-1",
        llm_config_version=1,
    )

    result = JobRunner(Repository(), Settings(_env_file=None)).run(job)  # type: ignore[arg-type]

    assert result == {
        "projectId": "project-1",
        "stage": "STRUCTURING",
        "stageStatus": "waiting_user",
        "gateErrors": ["交互逻辑尚未明确", "操作影响尚不可追溯"],
    }


def test_job_runner_processes_attachments_once(tmp_path) -> None:
    project_id = "project-1"
    stored_path = f"{project_id}/attachment-1-brief.md"
    path = tmp_path / stored_path
    path.parent.mkdir()
    path.write_text("# Brief\n\n附件需求", encoding="utf-8")
    state = ProjectState(project_id=project_id)
    attachment = SimpleNamespace(
        id="attachment-1",
        project_id=project_id,
        original_filename="brief.md",
        stored_path=stored_path,
        content_type="text/markdown",
        size_bytes=12,
        sha256="a" * 64,
        kind="text",
        status="pending",
        extracted_text=None,
        error_message=None,
    )

    class Repository:
        def list_project_attachments(self, requested_project_id: str):
            assert requested_project_id == project_id
            return [attachment]

        def update_project_attachment(
            self,
            attachment_id: str,
            *,
            status: str,
            extracted_text: str | None,
            error_message: str | None,
        ):
            assert attachment_id == "attachment-1"
            attachment.status = status
            attachment.extracted_text = extracted_text
            attachment.error_message = error_message
            return attachment

        def get_project(self, requested_project_id: str) -> ProjectState:
            assert requested_project_id == project_id
            return state

        def save_project(self, updated: ProjectState) -> None:
            assert updated is state

    runner = JobRunner(
        Repository(),  # type: ignore[arg-type]
        Settings(_env_file=None, upload_dir=tmp_path),
    )

    runner._process_project_attachments(project_id, object(), [attachment])
    runner._process_project_attachments(project_id, object(), [attachment])

    sources = state.requirement_spec.source_inputs
    assert len(sources) == 1
    assert sources[0].attachment_id == "attachment-1"
    assert "附件需求" in sources[0].text
