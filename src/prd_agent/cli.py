from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from alembic import command
from alembic.config import Config
from pwdlib import PasswordHash
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from prd_agent.agents import AgentFactory
from prd_agent.flow import WorkflowEngine
from prd_agent.gates import WorkflowGateError
from prd_agent.models import ArtifactType, ItemStatus, ProjectState, Stage
from prd_agent.repositories import (
    ArtifactNotFoundError,
    ProjectNotFoundError,
    SQLAlchemyRepository,
)
from prd_agent.settings import Settings, get_settings
from prd_agent.tasks import CrewAITaskExecutor
from prd_agent.worker import run_worker

app = typer.Typer(
    name="prd-agent",
    help="将模糊需求推进为终审通过的PRD和可执行SDD。",
    no_args_is_help=True,
)
console = Console()


def _repository(settings: Settings) -> SQLAlchemyRepository:
    if not settings.database_url:
        raise ValueError(
            "缺少 DATABASE_URL。请先通过 Web 安装向导或 .env 配置 MySQL。"
        )
    return SQLAlchemyRepository.from_url(
        settings.database_url,
        connect_timeout=settings.database_connect_timeout_seconds,
        read_timeout=settings.database_read_timeout_seconds,
    )


def _workflow(settings: Settings) -> WorkflowEngine:
    executor = CrewAITaskExecutor(AgentFactory(settings))
    return WorkflowEngine(
        repository=_repository(settings),
        executor=executor,
        max_prd_revision_rounds=settings.max_prd_revision_rounds,
    )


def _run(action):
    try:
        return action()
    except (
        ArtifactNotFoundError,
        ProjectNotFoundError,
        WorkflowGateError,
        ValueError,
    ) as exc:
        console.print(f"[red]错误：[/red]{exc}")
        raise typer.Exit(code=1) from exc


@app.command("new")
def new_project(
    requirement: Annotated[
        str | None,
        typer.Option("--requirement", "-r", help="初始需求描述"),
    ] = None,
) -> None:
    """创建项目并执行第一轮需求结构化。"""

    text = requirement or typer.prompt("请输入产品需求")
    state = _run(lambda: _workflow(get_settings()).create_project(text))
    _render_state(state)


@app.command("resume")
def resume_project(
    project_id: Annotated[str, typer.Argument(help="项目ID")],
    user_input: Annotated[
        str | None,
        typer.Option("--input", "-i", help="回答、确认命令或重试命令"),
    ] = None,
) -> None:
    """恢复项目，提交一轮回答或确认。"""

    text = user_input or typer.prompt("请输入回答或命令")
    state = _run(
        lambda: _workflow(get_settings()).submit_user_input(project_id, text)
    )
    _render_state(state)


@app.command("status")
def project_status(
    project_id: Annotated[str, typer.Argument(help="项目ID")],
) -> None:
    """查看项目阶段、问题和文档版本。"""

    settings = get_settings()
    state = _run(lambda: _repository(settings).get_project(project_id))
    _render_state(state)


@app.command("export")
def export_artifact(
    project_id: Annotated[str, typer.Argument(help="项目ID")],
    artifact: Annotated[
        str,
        typer.Option("--artifact", "-a", help="prd 或 sdd"),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="输出路径"),
    ] = None,
) -> None:
    """导出最新PRD或SDD Markdown。"""

    try:
        artifact_type = ArtifactType(artifact.casefold())
    except ValueError as exc:
        console.print("[red]错误：[/red]--artifact 只能是 prd 或 sdd")
        raise typer.Exit(code=1) from exc
    if artifact_type not in {ArtifactType.PRD, ArtifactType.SDD}:
        raise typer.BadParameter("--artifact 只能是 prd 或 sdd")

    settings = get_settings()
    record = _run(
        lambda: _repository(settings).get_latest_artifact(
            project_id, artifact_type
        )
    )
    destination = output or (
        settings.project_root
        / "output"
        / project_id
        / f"{artifact_type.value}-v{record.version}.md"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(record.content, encoding="utf-8")
    console.print(f"[green]已导出：[/green]{destination}")


@app.command("db-upgrade")
def database_upgrade() -> None:
    """将数据库迁移到最新版本。"""

    settings = get_settings()
    if not settings.database_url:
        console.print("[red]错误：[/red]缺少 DATABASE_URL，请先完成数据库配置。")
        raise typer.Exit(code=1)
    config = Config(str(settings.project_root / "alembic.ini"))
    config.set_main_option("script_location", str(settings.project_root / "alembic"))
    config.set_main_option(
        "sqlalchemy.url",
        settings.database_url.replace("%", "%%"),
    )
    command.upgrade(config, "head")
    console.print("[green]数据库迁移完成。[/green]")


@app.command("reset-admin-password")
def reset_admin_password() -> None:
    """交互式重置管理员密码，并注销所有现有会话。"""

    password = typer.prompt(
        "请输入新密码",
        hide_input=True,
        confirmation_prompt="请再次输入新密码",
    )
    if not 8 <= len(password) <= 128:
        console.print("[red]错误：[/red]密码长度必须为 8 至 128 个字符。")
        raise typer.Exit(code=1)

    repository = _run(lambda: _repository(get_settings()))
    password_hash = PasswordHash.recommended().hash(password)
    updated = _run(lambda: repository.reset_admin_password(password_hash))
    if not updated:
        console.print("[red]错误：[/red]尚未创建管理员，请先在登录页创建管理员。")
        raise typer.Exit(code=1)
    console.print("[green]管理员密码已重置，所有现有登录会话已失效。[/green]")


@app.command("api")
def run_api() -> None:
    """启动仅监听localhost的Web API。"""

    settings = get_settings()
    from prd_agent.api import create_app

    uvicorn.run(
        create_app(settings),
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


@app.command("worker")
def worker(
    once: Annotated[
        bool,
        typer.Option("--once", help="最多处理一个任务后退出"),
    ] = False,
) -> None:
    """启动MySQL后台任务Worker。"""

    run_worker(get_settings(), once=once)


def _render_state(state: ProjectState) -> None:
    summary = (
        f"项目ID：{state.project_id}\n"
        f"阶段：{state.stage}\n"
        f"状态：{state.stage_status}\n"
        f"轮次：{state.round_number}"
    )
    console.print(Panel(summary, title="项目状态"))

    if state.stage == Stage.STRUCTURING:
        table = Table(title="待澄清问题")
        table.add_column("编号")
        table.add_column("类型")
        table.add_column("问题")
        table.add_column("重要性")
        for item in state.questions:
            if item.status == ItemStatus.OPEN:
                table.add_row(
                    item.question_id,
                    item.question_type,
                    item.description,
                    item.importance,
                )
        console.print(table)
        if not any(item.status == ItemStatus.OPEN for item in state.questions):
            console.print("信息已完整，输入 [bold]下一步[/bold] 进入逻辑校验。")

    if state.stage == Stage.LOGIC_VALIDATING:
        table = Table(title="逻辑问题")
        table.add_column("编号")
        table.add_column("维度")
        table.add_column("严重程度")
        table.add_column("状态")
        table.add_column("问题")
        for item in state.logic_issues:
            table.add_row(
                item.issue_id,
                item.dimension,
                str(item.severity),
                str(item.status),
                item.description,
            )
        console.print(table)
        console.print(
            "逐条回答；重要问题可输入“豁免 L-001: 原因”；"
            "门禁通过后输入 [bold]下一步[/bold]。"
        )

    if state.stage == Stage.PRD_TYPE_CONFIRMING and state.product_type:
        secondary = "、".join(str(item) for item in state.product_type.secondary) or "无"
        console.print(
            Panel(
                f"主类型：{state.product_type.primary}\n"
                f"次类型：{secondary}\n"
                f"理由：{state.product_type.rationale}",
                title="产品类型识别",
            )
        )
        console.print("输入 [bold]下一步[/bold] 确认，或输入修正意见。")

    if state.stage == Stage.SDD_CONFIRMING:
        console.print("PRD终审已通过，输入 [bold]下一步[/bold] 生成SDD。")

    if state.stage == Stage.COMPLETED:
        console.print(
            "[green]流程完成。[/green] "
            "使用 `prd-agent export <项目ID> --artifact prd|sdd` 导出文档。"
        )


if __name__ == "__main__":
    app()
