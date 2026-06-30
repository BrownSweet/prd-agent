from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url

from prd_agent.flow import WorkflowEngine
from prd_agent.models import (
    BusinessRule,
    ClarificationQuestion,
    CompletenessAssessment,
    DataSourceDefinition,
    DependencyDefinition,
    InteractionDefinition,
    LogicIssue,
    LogicValidationResult,
    OperationImpact,
    PrdResult,
    PrdReviewResult,
    ProductTypeCode,
    ProductTypeResult,
    ProductTypeSelection,
    ProjectState,
    RequirementFeature,
    RequirementModule,
    RequirementSpec,
    RequirementStateDefinition,
    RequirementStructureResult,
    ReviewDimension,
    ReviewIssue,
    SddModule,
    SddResult,
    Severity,
)
from prd_agent.repositories import SQLAlchemyRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TABLES = (
    "admin_sessions",
    "admin_users",
    "app_settings",
    "workflow_events",
    "approvals",
    "artifacts",
    "logic_issues",
    "questions",
    "requirement_snapshots",
    "project_attachments",
    "workflow_jobs",
    "projects",
    "llm_configs",
)


def complete_spec() -> RequirementSpec:
    return RequirementSpec(
        title="需求到SDD工作流",
        summary="把模糊需求推进为可开发文档",
        modules=[
            RequirementModule(
                name="工作流",
                description="管理需求文档生命周期",
                features=[
                    RequirementFeature(
                        name="推进阶段",
                        description="按门禁推进项目",
                        data_source="项目状态库",
                        interaction_logic="用户回答或确认后系统校验门禁",
                        operation_impact="更新项目状态并记录审计事件",
                        dependencies=["MySQL"],
                    )
                ],
            )
        ],
        data_sources=[
            DataSourceDefinition(
                name="项目状态库",
                source_type="MySQL",
                owner="产品团队",
                freshness="实时",
            )
        ],
        interactions=[
            InteractionDefinition(
                trigger="用户提交回答",
                system_behavior="重新执行当前阶段",
                feedback="展示剩余问题",
            )
        ],
        operation_impacts=[
            OperationImpact(
                operation="确认下一步",
                affected_targets=["项目阶段", "审计记录"],
                timing="立即",
                reversible=False,
            )
        ],
        dependencies=[
            DependencyDefinition(
                upstream="当前阶段门禁",
                downstream="下一阶段",
                relationship="前置",
                deletion_impact="项目不能继续推进",
            )
        ],
        states=[
            RequirementStateDefinition(
                name="waiting_user",
                entry_condition="阶段需要用户输入",
                exit_condition="用户提交有效回答或确认",
            )
        ],
        business_rules=[
            BusinessRule(rule_id="R-001", description="阻断问题未解决不得推进")
        ],
        exceptions=["LLM失败时阶段标记failed"],
        completeness=CompletenessAssessment(
            modules_complete=True,
            data_sources_clear=True,
            interactions_clear=True,
            impacts_traceable=True,
            dependencies_clear=True,
        ),
    )


PRD_HEADINGS = [
    "文档信息",
    "修订历史",
    "项目背景与目标",
    "核心名词定义",
    "功能需求总览",
    "详细功能需求",
    "非功能需求",
    "全局交互规范",
    "附录",
]
SDD_HEADINGS = [
    "功能契约",
    "页面结构与组件树",
    "数据模型定义",
    "API接口定义",
    "数据库表设计",
    "核心交互流程",
    "测试验收标准",
    "技术决策与约束",
]


def document(headings: list[str], marker: str) -> str:
    return "\n\n".join(f"## {heading}\n\n{marker}" for heading in headings)


class FakeTaskExecutor:
    def __init__(self):
        self.structure_calls = 0
        self.logic_calls = 0
        self.review_calls = 0
        self.generate_sdd_calls = 0

    def structure_requirements(
        self, state: ProjectState
    ) -> RequirementStructureResult:
        self.structure_calls += 1
        if self.structure_calls == 1:
            spec = complete_spec()
            spec.completeness.modules_complete = False
            return RequirementStructureResult(
                requirement_spec=spec,
                questions=[
                    ClarificationQuestion(
                        question_id="Q-999",
                        question_type="模块",
                        description="需要覆盖哪些模块？",
                        importance="决定产品范围",
                    )
                ],
                summary_markdown="第一轮",
            )
        return RequirementStructureResult(
            requirement_spec=complete_spec(),
            questions=[],
            resolved_question_ids=["Q-001"],
            summary_markdown="信息完整",
        )

    def validate_logic(self, state: ProjectState) -> LogicValidationResult:
        self.logic_calls += 1
        if self.logic_calls == 1:
            return LogicValidationResult(
                requirement_spec=complete_spec(),
                issues=[
                    LogicIssue(
                        issue_id="L-999",
                        dimension="状态流转",
                        description="失败后如何恢复？",
                        severity=Severity.BLOCKING,
                    )
                ],
                summary_markdown="发现阻断问题",
            )
        spec = complete_spec()
        spec.business_rules.append(
            BusinessRule(rule_id="R-002", description="失败后允许用户重试")
        )
        return LogicValidationResult(
            requirement_spec=spec,
            issues=[],
            resolved_issue_ids=["L-001"],
            summary_markdown="阻断问题已解决",
        )

    def identify_product_type(self, state: ProjectState) -> ProductTypeResult:
        return ProductTypeResult(
            product_type=ProductTypeSelection(
                primary=ProductTypeCode.ADMIN,
                secondary=[ProductTypeCode.API],
                matched_features=["项目列表", "工作流服务"],
                rationale="管理界面为主，同时提供流程服务",
            ),
            summary_markdown="A+C",
        )

    def write_prd(self, state: ProjectState) -> PrdResult:
        return PrdResult(
            markdown=document(PRD_HEADINGS, "PRD v1"),
            business_rules=complete_spec().business_rules,
        )

    def review_prd(self, state: ProjectState, prd: str) -> PrdReviewResult:
        self.review_calls += 1
        dimensions = [
            ReviewDimension(
                dimension=name,
                passed=self.review_calls > 1,
                explanation="通过" if self.review_calls > 1 else "需补充",
            )
            for name in (
                "逻辑准确性",
                "流程闭环性",
                "场景覆盖度",
                "交互统一性",
                "用户使用逻辑",
            )
        ]
        if self.review_calls == 1:
            return PrdReviewResult(
                passed=False,
                dimensions=dimensions,
                issues=[
                    ReviewIssue(
                        issue_id="L-001",
                        description="缺少恢复流程",
                        blocking=True,
                        suggestion_type="流程闭环",
                    )
                ],
                report_markdown="终审未通过",
            )
        return PrdReviewResult(
            passed=True,
            dimensions=dimensions,
            issues=[],
            report_markdown="终审通过",
        )

    def revise_prd(
        self, state: ProjectState, prd: str, review: str
    ) -> PrdResult:
        return PrdResult(
            markdown=document(PRD_HEADINGS, "PRD v2，包含恢复流程"),
            business_rules=[
                *complete_spec().business_rules,
                BusinessRule(rule_id="R-002", description="失败后允许重试"),
            ],
        )

    def generate_sdd(self, state: ProjectState, prd: str) -> SddResult:
        self.generate_sdd_calls += 1
        module = SddModule(
            name="工作流",
            markdown=document(SDD_HEADINGS, "技术契约"),
        )
        return SddResult(
            markdown="SDD总览",
            modules=[module],
            technical_defaults=["React 18", "Go 1.21+", "MySQL 8.0+"],
        )


@pytest.fixture(scope="session")
def test_database_url() -> str:
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.fail(
            "数据库测试需要 TEST_DATABASE_URL，例如 "
            "mysql+pymysql://USER:PASSWORD@HOST:3306/prd_agent_test?charset=utf8mb4"
        )

    url = make_url(value)
    if url.get_backend_name() != "mysql" or url.drivername != "mysql+pymysql":
        pytest.fail("TEST_DATABASE_URL 必须使用 mysql+pymysql")
    if not (url.database or "").endswith("_test"):
        pytest.fail("测试数据库名称必须以 _test 结尾")
    if url.query.get("charset") != "utf8mb4":
        pytest.fail("TEST_DATABASE_URL 必须包含 charset=utf8mb4")

    production = os.getenv("DATABASE_URL")
    if production:
        production_url = make_url(production)
        production_target = (
            production_url.host,
            production_url.port or 3306,
            production_url.database,
        )
        test_target = (url.host, url.port or 3306, url.database)
        if production_target == test_target:
            pytest.fail("DATABASE_URL 与 TEST_DATABASE_URL 不能指向同一数据库")
    return value


@pytest.fixture(scope="session")
def migrated_database(test_database_url: str) -> str:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option(
        "sqlalchemy.url",
        test_database_url.replace("%", "%%"),
    )
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    repository = SQLAlchemyRepository.from_url(test_database_url)
    with repository.engine.connect() as connection:
        version = str(connection.scalar(text("SELECT VERSION()")))
        if "mariadb" in version.casefold():
            pytest.fail(f"测试数据库必须是MySQL 8.0+，不支持MariaDB：{version}")
        major = int(version.split(".", maxsplit=1)[0])
        if major < 8:
            pytest.fail(f"测试数据库必须是MySQL 8.0+，当前版本：{version}")

    yield test_database_url
    command.downgrade(config, "base")


def clean_database(repository: SQLAlchemyRepository) -> None:
    with repository.engine.begin() as connection:
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        try:
            for table in TABLES:
                connection.execute(text(f"TRUNCATE TABLE `{table}`"))
        finally:
            connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


@pytest.fixture
def repository(migrated_database: str) -> SQLAlchemyRepository:
    repo = SQLAlchemyRepository.from_url(migrated_database)
    clean_database(repo)
    yield repo
    clean_database(repo)
    repo.engine.dispose()


@pytest.fixture
def fake_executor() -> FakeTaskExecutor:
    return FakeTaskExecutor()


@pytest.fixture
def workflow(
    repository: SQLAlchemyRepository,
    fake_executor: FakeTaskExecutor,
) -> WorkflowEngine:
    return WorkflowEngine(repository, fake_executor, max_prd_revision_rounds=3)
