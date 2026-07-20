from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from prd_agent.api import (
    _allowed_actions,
    _assert_advance_allowed,
    _gate_errors,
    _rollback_targets,
    create_app,
)
from prd_agent.gates import WorkflowGateError
from prd_agent.models import ProjectState, Stage, StageStatus
from prd_agent.repositories import SQLAlchemyRepository
from prd_agent.settings import Settings

PRODUCTION_URL = (
    "mysql+pymysql://user:password@localhost:3306/prd_agent?charset=utf8mb4"
)
TEST_URL = (
    "mysql+pymysql://user:password@localhost:3306/prd_agent_test?charset=utf8mb4"
)


def api_settings(test_database_url: str) -> Settings:
    url = make_url(test_database_url)
    shadow_url = url.set(database=f"{url.database}_other_test").render_as_string(
        hide_password=False
    )
    return Settings(
        _env_file=None,
        database_url=test_database_url,
        test_database_url=shadow_url,
        llm_model="deepseek/deepseek-chat",
        llm_api_key="sk-api-test-secret",
    )


def test_failed_prd_review_allows_retry_and_feedback_action() -> None:
    state = ProjectState(
        stage=Stage.PRD_REVIEWING,
        stage_status=StageStatus.FAILED,
    )

    assert _allowed_actions(state, None, None) == [
        "retry",
        "feedback",
        "overrideReview",
        "rollback",
    ]
    assert _rollback_targets(state) == [
        {
            "stage": "PRD_REVISING",
            "label": "回到PRD修订",
            "description": "基于当前PRD和终审报告生成新版PRD",
        },
        {
            "stage": "LOGIC_VALIDATING",
            "label": "回到逻辑校验",
            "description": "把终审阻断问题纳入需求逻辑后重新执行7维扫描",
        },
    ]


def test_sdd_confirmation_allows_controlled_rollback_targets() -> None:
    state = ProjectState(
        stage=Stage.SDD_CONFIRMING,
        stage_status=StageStatus.WAITING_USER,
    )

    assert _allowed_actions(state, None, None) == ["advance", "rollback"]
    assert _rollback_targets(state) == [
        {
            "stage": "PRD_REVISING",
            "label": "回到PRD修订",
            "description": "基于当前PRD和终审报告生成新版PRD",
        },
        {
            "stage": "PRD_TYPE_CONFIRMING",
            "label": "回到产品类型确认",
            "description": "重新识别产品类型并重新生成PRD",
        },
    ]


def test_completed_project_with_sdd_allows_regenerate_sdd() -> None:
    state = ProjectState(
        stage=Stage.COMPLETED,
        stage_status=StageStatus.COMPLETED,
        artifact_versions={"sdd": 1},
    )

    assert _allowed_actions(state, None, None) == ["regenerateSdd"]


def test_advance_precheck_rejects_incomplete_structured_requirement() -> None:
    state = ProjectState(
        stage=Stage.STRUCTURING,
        stage_status=StageStatus.WAITING_USER,
    )

    with pytest.raises(WorkflowGateError) as raised:
        _assert_advance_allowed(state)

    assert "交互逻辑尚未明确" in raised.value.errors
    assert "操作影响尚不可追溯" in raised.value.errors


def test_incomplete_structuring_exposes_gate_errors_and_hides_advance() -> None:
    state = ProjectState(
        stage=Stage.STRUCTURING,
        stage_status=StageStatus.WAITING_USER,
    )

    assert "交互逻辑尚未明确" in _gate_errors(state)
    assert "操作影响尚不可追溯" in _gate_errors(state)
    assert _allowed_actions(state, None, None) == ["answer", "feedback"]


def test_api_enters_setup_mode_without_database_configuration() -> None:
    app = create_app(
        Settings(_env_file=None, database_url=None, test_database_url=None)
    )

    with TestClient(app) as client:
        status = client.get("/api/v1/setup/status")
        projects = client.get("/api/v1/projects")

        assert status.status_code == 200
        assert status.json()["data"]["setupRequired"] is True
        assert projects.status_code == 503
        assert projects.json()["code"] == "setup_required"


def test_setup_database_test_rejects_mixed_database_types() -> None:
    app = create_app(
        Settings(_env_file=None, database_url=None, test_database_url=None)
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/setup/database/test",
            json={
                "databaseUrl": "sqlite+pysqlite:///./data/prd_agent.db",
                "testDatabaseUrl": TEST_URL,
            },
        )

        assert response.status_code == 400
        assert "相同数据库类型" in response.json()["message"]


def test_setup_database_test_accepts_sqlite_urls(tmp_path) -> None:
    app = create_app(
        Settings(_env_file=None, database_url=None, test_database_url=None)
    )
    database_url = f"sqlite+pysqlite:///{tmp_path / 'prd_agent.db'}"
    test_database_url = f"sqlite+pysqlite:///{tmp_path / 'prd_agent_test.db'}"

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/setup/database/test",
            json={
                "databaseUrl": database_url,
                "testDatabaseUrl": test_database_url,
            },
        )

    assert response.status_code == 200
    assert response.json()["data"]["ok"] is True


def test_setup_database_save_preserves_env_and_upserts_database_urls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    settings = Settings(
        _env_file=None,
        database_url=None,
        test_database_url=None,
        project_root=tmp_path,
    )
    env_path = tmp_path / ".env"
    env_path.write_text(
        "LLM_MODEL=deepseek/deepseek-chat\n"
        "DATABASE_URL=old\n"
        "CREWAI_TRACING_ENABLED=false\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("prd_agent.api._test_database_url", lambda *args: None)
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/setup/database/save",
            json={
                "databaseUrl": PRODUCTION_URL,
                "testDatabaseUrl": TEST_URL,
            },
        )

    assert response.status_code == 200
    assert response.json()["data"]["restartRequired"] is True
    content = env_path.read_text(encoding="utf-8")
    assert "LLM_MODEL=deepseek/deepseek-chat" in content
    assert f"DATABASE_URL={PRODUCTION_URL}" in content
    assert f"TEST_DATABASE_URL={TEST_URL}" in content
    assert "CREWAI_TRACING_ENABLED=false" in content


def test_api_creates_project_with_idempotent_queued_job(
    repository: SQLAlchemyRepository,
    test_database_url: str,
) -> None:
    app = create_app(api_settings(test_database_url), repository)
    headers = {"Idempotency-Key": "create-project-key-001"}

    with TestClient(app) as client:
        client.post(
            "/api/v1/auth/setup",
            json={"username": "admin", "password": "secure-password"},
        )
        response = client.post(
            "/api/v1/projects",
            headers=headers,
            json={"requirement": "做一个需求管理产品"},
        )
        repeated = client.post(
            "/api/v1/projects",
            headers=headers,
            json={"requirement": "这次输入应被幂等键忽略"},
        )

        assert response.status_code == 202
        assert repeated.status_code == 202
        assert repeated.json()["data"]["jobId"] == response.json()["data"]["jobId"]
        project_id = response.json()["data"]["projectId"]

        detail = client.get(f"/api/v1/projects/{project_id}")
        assert detail.status_code == 200
        assert detail.json()["data"]["activeJob"]["status"] == "queued"

        conflict = client.post(
            f"/api/v1/projects/{project_id}/advance",
            headers={"Idempotency-Key": "advance-project-key-001"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "active_job"


def test_api_creates_project_with_uploaded_attachment(
    repository: SQLAlchemyRepository,
    test_database_url: str,
    tmp_path,
) -> None:
    settings = api_settings(test_database_url).model_copy(
        update={"upload_dir": tmp_path}
    )
    app = create_app(settings, repository)
    headers = {"Idempotency-Key": "create-project-upload-001"}

    with TestClient(app) as client:
        client.post(
            "/api/v1/auth/setup",
            json={"username": "admin", "password": "secure-password"},
        )
        response = client.post(
            "/api/v1/projects",
            headers=headers,
            data={"requirement": "补充 Markdown 需求"},
            files={
                "files": (
                    "brief.md",
                    "# Brief\n\n上传内容".encode(),
                    "text/markdown",
                )
            },
        )
        repeated = client.post(
            "/api/v1/projects",
            headers=headers,
            data={"requirement": "不应创建第二个附件"},
            files={"files": ("other.md", b"ignored", "text/markdown")},
        )

        assert response.status_code == 202
        assert repeated.json()["data"]["jobId"] == response.json()["data"]["jobId"]
        project_id = response.json()["data"]["projectId"]

        attachments = repository.list_project_attachments(project_id)
        assert len(attachments) == 1
        assert attachments[0].original_filename == "brief.md"
        assert (tmp_path / attachments[0].stored_path).is_file()

        detail = client.get(f"/api/v1/projects/{project_id}")
        assert detail.status_code == 200
        assert detail.json()["data"]["attachments"][0]["filename"] == "brief.md"


def test_api_masks_keys_and_preserves_key_on_blank_update(
    repository: SQLAlchemyRepository,
    test_database_url: str,
) -> None:
    app = create_app(api_settings(test_database_url), repository)

    with TestClient(app) as client:
        client.post(
            "/api/v1/auth/setup",
            json={"username": "admin", "password": "secure-password"},
        )
        created = client.post(
            "/api/v1/llm-configs",
            headers={"Idempotency-Key": "create-config-key-001"},
            json={
                "name": "DeepSeek",
                "provider": "deepseek",
                "model": "deepseek-chat",
                "apiKey": "sk-very-secret-value",
                "temperature": 0.2,
                "timeoutSeconds": 120,
                "makeDefault": True,
            },
        )
        assert created.status_code == 200
        payload = created.json()["data"]
        assert "apiKey" not in payload
        assert payload["apiKeyMask"].startswith("sk-")
        config_id = payload["id"]

        updated = client.put(
            f"/api/v1/llm-configs/{config_id}",
            headers={"Idempotency-Key": "update-config-key-001"},
            json={
                "name": "DeepSeek Updated",
                "provider": "deepseek",
                "model": "deepseek-chat",
                "temperature": 0.3,
                "timeoutSeconds": 90,
                "makeDefault": True,
            },
        )
        assert updated.status_code == 200
        assert repository.get_llm_config(config_id).api_key == "sk-very-secret-value"

        listed = client.get("/api/v1/llm-configs?include_archived=true")
        raw = listed.text
        assert "sk-very-secret-value" not in raw
        assert '"apiKey"' not in raw


def test_admin_setup_login_logout_and_api_protection(
    repository: SQLAlchemyRepository,
    test_database_url: str,
) -> None:
    app = create_app(api_settings(test_database_url), repository)

    with TestClient(app) as client:
        status = client.get("/api/v1/auth/status")
        blocked = client.get("/api/v1/projects")

        assert status.json()["data"] == {
            "adminConfigured": False,
            "authenticated": False,
            "username": None,
        }
        assert blocked.status_code == 403
        assert blocked.json()["code"] == "admin_setup_required"

        created = client.post(
            "/api/v1/auth/setup",
            json={"username": " admin ", "password": "secure-password"},
        )
        assert created.status_code == 201
        assert created.json()["data"]["username"] == "admin"
        cookie = created.headers["set-cookie"]
        assert "prd_agent_session=" in cookie
        assert "HttpOnly" in cookie
        assert "SameSite=strict" in cookie
        assert "Max-Age=604800" in cookie

        with repository.engine.connect() as connection:
            password_hash = connection.scalar(
                text("SELECT password_hash FROM admin_users WHERE id = 1")
            )
            token_hash = connection.scalar(
                text("SELECT token_hash FROM admin_sessions LIMIT 1")
            )
        assert password_hash != "secure-password"
        assert str(password_hash).startswith("$argon2")
        assert len(str(token_hash)) == 64
        assert client.cookies["prd_agent_session"] != token_hash

        duplicate = client.post(
            "/api/v1/auth/setup",
            json={"username": "other", "password": "another-password"},
        )
        assert duplicate.status_code == 409

        allowed = client.get("/api/v1/projects")
        assert allowed.status_code == 200

        logged_out = client.post("/api/v1/auth/logout")
        assert logged_out.status_code == 200
        assert logged_out.json()["data"]["authenticated"] is False
        assert client.get("/api/v1/projects").status_code == 401

        wrong = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "wrong-password"},
        )
        assert wrong.status_code == 401
        assert wrong.json()["message"] == "用户名或密码错误"

        logged_in = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "secure-password"},
        )
        assert logged_in.status_code == 200
        assert logged_in.json()["data"]["authenticated"] is True
        assert client.get("/api/v1/projects").status_code == 200


def test_expired_admin_session_is_rejected(
    repository: SQLAlchemyRepository,
    test_database_url: str,
) -> None:
    app = create_app(api_settings(test_database_url), repository)

    with TestClient(app) as client:
        client.post(
            "/api/v1/auth/setup",
            json={"username": "admin", "password": "secure-password"},
        )
        with repository.engine.begin() as connection:
            connection.execute(
                text("UPDATE admin_sessions SET expires_at = :expires_at"),
                {
                    "expires_at": datetime.now(timezone.utc)
                    - timedelta(seconds=1)
                },
            )

        response = client.get("/api/v1/projects")

        assert response.status_code == 401
        assert response.json()["code"] == "authentication_required"
