from __future__ import annotations

import pytest

from prd_agent.flow import WorkflowEngine
from prd_agent.gates import WorkflowGateError
from prd_agent.models import (
    ArtifactType,
    RequirementStructureResult,
    ItemStatus,
    PrdReviewResult,
    ProjectState,
    ReviewDimension,
    ReviewIssue,
    Stage,
    StageStatus,
)
from prd_agent.repositories import SQLAlchemyRepository

from conftest import FakeTaskExecutor


class AlwaysFailingReviewExecutor(FakeTaskExecutor):
    def review_prd(self, state, prd: str) -> PrdReviewResult:
        self.review_calls += 1
        dimensions = [
            ReviewDimension(
                dimension=name,
                passed=False,
                explanation="仍需修订",
            )
            for name in (
                "逻辑准确性",
                "流程闭环性",
                "场景覆盖度",
                "交互统一性",
                "用户使用逻辑",
            )
        ]
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


class IncompleteStructuringExecutor(FakeTaskExecutor):
    def structure_requirements(
        self, state: ProjectState
    ) -> RequirementStructureResult:
        spec = state.requirement_spec.model_copy(deep=True)
        spec.completeness.modules_complete = True
        spec.completeness.data_sources_clear = True
        spec.completeness.dependencies_clear = True
        spec.completeness.interactions_clear = False
        spec.completeness.impacts_traceable = False
        return RequirementStructureResult(
            requirement_spec=spec,
            questions=[],
            summary_markdown="本轮结构化完成",
        )


class MemoryRepository:
    def __init__(self, state: ProjectState):
        self.state = state
        self.events = []
        self.snapshots = 0

    def get_project(self, project_id: str) -> ProjectState:
        assert project_id == self.state.project_id
        return self.state

    def save_project(self, state: ProjectState) -> None:
        self.state = state

    def add_event(self, project_id: str, event) -> None:
        assert project_id == self.state.project_id
        self.events.append(event)

    def save_requirement_snapshot(self, state: ProjectState) -> None:
        assert state.project_id == self.state.project_id
        self.snapshots += 1


def advance_to_product_type_confirmation(
    workflow: WorkflowEngine,
) -> ProjectState:
    state = workflow.create_project("做一个需求到SDD的产品")
    state = workflow.submit_user_input(state.project_id, "覆盖完整五阶段")
    state = workflow.submit_user_input(state.project_id, "下一步")
    state = workflow.submit_user_input(
        state.project_id,
        "失败后保留状态，允许用户重试",
    )
    return workflow.submit_user_input(state.project_id, "下一步")


def test_structuring_adds_questions_when_gate_fails_without_model_questions() -> None:
    state = ProjectState()
    repository = MemoryRepository(state)
    workflow = WorkflowEngine(repository, IncompleteStructuringExecutor())

    result = workflow.advance(state.project_id)

    assert result.stage == Stage.STRUCTURING
    assert result.stage_status == StageStatus.WAITING_USER
    descriptions = [item.description for item in result.questions]
    assert any("交互逻辑" in item for item in descriptions)
    assert any("操作影响" in item for item in descriptions)


def test_full_workflow_persists_and_revises_prd(
    workflow: WorkflowEngine,
    repository: SQLAlchemyRepository,
    fake_executor: FakeTaskExecutor,
) -> None:
    state = workflow.create_project("做一个需求到SDD的产品")
    assert state.stage == Stage.STRUCTURING
    assert state.stage_status == StageStatus.WAITING_USER
    assert state.questions[0].question_id == "Q-001"

    restored = repository.get_project(state.project_id)
    assert restored.questions[0].description == "需要覆盖哪些模块？"

    state = workflow.submit_user_input(state.project_id, "覆盖完整五阶段")
    assert state.stage == Stage.STRUCTURING
    assert state.questions[0].status == ItemStatus.RESOLVED

    state = workflow.submit_user_input(state.project_id, "下一步")
    assert state.stage == Stage.LOGIC_VALIDATING
    assert state.logic_issues[0].issue_id == "L-001"

    with pytest.raises(WorkflowGateError, match="阻断"):
        workflow.submit_user_input(state.project_id, "下一步")

    state = workflow.submit_user_input(
        state.project_id, "失败后保留状态，允许用户重试"
    )
    assert state.logic_issues[0].status == ItemStatus.RESOLVED

    state = workflow.submit_user_input(state.project_id, "下一步")
    assert state.stage == Stage.PRD_TYPE_CONFIRMING
    assert str(state.product_type.primary) == "A"
    assert [str(item) for item in state.product_type.secondary] == ["C"]

    state = workflow.submit_user_input(state.project_id, "下一步")
    assert state.stage == Stage.SDD_CONFIRMING
    assert state.artifact_versions["prd"] == 2
    assert state.artifact_versions["prd-review"] == 2
    assert fake_executor.review_calls == 2
    assert fake_executor.generate_sdd_calls == 0

    state = workflow.submit_user_input(state.project_id, "下一步")
    assert state.stage == Stage.COMPLETED
    assert state.stage_status == StageStatus.COMPLETED
    assert state.artifact_versions["sdd"] == 1
    assert fake_executor.generate_sdd_calls == 1

    prd = repository.get_latest_artifact(state.project_id, ArtifactType.PRD)
    sdd = repository.get_latest_artifact(state.project_id, ArtifactType.SDD)
    assert prd.version == 2
    assert "恢复流程" in prd.content
    assert "# 工作流" in sdd.content
    assert "## 功能契约" in sdd.content
    assert "## 技术决策与约束" in sdd.content
    assert sdd.content != "SDD总览"
    assert sdd.metadata_json["prdVersion"] == 2


def test_one_revision_round_allows_one_revised_prd(
    repository: SQLAlchemyRepository,
) -> None:
    fake_executor = FakeTaskExecutor()
    workflow = WorkflowEngine(
        repository,
        fake_executor,
        max_prd_revision_rounds=1,
    )

    state = advance_to_product_type_confirmation(workflow)
    state = workflow.submit_user_input(state.project_id, "下一步")

    assert state.stage == Stage.SDD_CONFIRMING
    assert state.artifact_versions["prd"] == 2
    assert state.artifact_versions["prd-review"] == 2
    assert fake_executor.review_calls == 2


def test_retry_failed_prd_review_revises_before_reviewing_again(
    repository: SQLAlchemyRepository,
) -> None:
    fake_executor = AlwaysFailingReviewExecutor()
    workflow = WorkflowEngine(
        repository,
        fake_executor,
        max_prd_revision_rounds=1,
    )

    state = advance_to_product_type_confirmation(workflow)
    state = workflow.submit_user_input(state.project_id, "下一步")

    assert state.stage == Stage.PRD_REVIEWING
    assert state.stage_status == StageStatus.FAILED
    assert state.artifact_versions["prd"] == 2

    state = workflow.submit_user_input(state.project_id, "重试")
    prd = repository.get_latest_artifact(state.project_id, ArtifactType.PRD)

    assert state.stage == Stage.PRD_REVIEWING
    assert state.stage_status == StageStatus.FAILED
    assert prd.version == 3
    assert fake_executor.review_calls == 3


def test_feedback_on_failed_prd_review_creates_revised_prd(
    repository: SQLAlchemyRepository,
) -> None:
    fake_executor = AlwaysFailingReviewExecutor()
    workflow = WorkflowEngine(
        repository,
        fake_executor,
        max_prd_revision_rounds=1,
    )

    state = advance_to_product_type_confirmation(workflow)
    state = workflow.submit_user_input(state.project_id, "下一步")

    assert state.stage == Stage.PRD_REVIEWING
    assert state.stage_status == StageStatus.FAILED

    feedback = "请补充原始消息持久化和重启恢复机制"
    state = workflow.submit_user_input(state.project_id, feedback)
    prd = repository.get_latest_artifact(state.project_id, ArtifactType.PRD)
    stored = repository.get_project(state.project_id)

    assert state.stage == Stage.PRD_REVIEWING
    assert state.stage_status == StageStatus.FAILED
    assert prd.version == 3
    assert fake_executor.review_calls == 3
    assert any(
        source.text == feedback
        for source in stored.requirement_spec.source_inputs
    )


def test_rollback_from_failed_prd_review_to_logic_validation(
    repository: SQLAlchemyRepository,
) -> None:
    fake_executor = AlwaysFailingReviewExecutor()
    workflow = WorkflowEngine(
        repository,
        fake_executor,
        max_prd_revision_rounds=1,
    )

    state = advance_to_product_type_confirmation(workflow)
    state = workflow.submit_user_input(state.project_id, "下一步")

    assert state.stage == Stage.PRD_REVIEWING
    assert state.stage_status == StageStatus.FAILED
    assert state.artifact_versions["prd"] == 2
    assert any(approval.kind == "product_type" for approval in state.approvals)

    feedback = "终审阻断问题需要回到逻辑校验重新处理"
    state = workflow.rollback(state.project_id, Stage.LOGIC_VALIDATING, feedback)
    stored = repository.get_project(state.project_id)

    assert state.stage == Stage.LOGIC_VALIDATING
    assert state.stage_status == StageStatus.WAITING_USER
    assert fake_executor.logic_calls == 3
    assert state.product_type is None
    assert "prd" not in state.artifact_versions
    assert "prd-review" not in state.artifact_versions
    assert all(
        approval.stage != Stage.PRD_TYPE_CONFIRMING
        for approval in state.approvals
    )
    assert any(
        source.text == feedback
        for source in stored.requirement_spec.source_inputs
    )


def test_override_failed_prd_review_moves_to_sdd_confirmation(
    repository: SQLAlchemyRepository,
) -> None:
    fake_executor = AlwaysFailingReviewExecutor()
    workflow = WorkflowEngine(
        repository,
        fake_executor,
        max_prd_revision_rounds=1,
    )

    state = advance_to_product_type_confirmation(workflow)
    state = workflow.submit_user_input(state.project_id, "下一步")

    assert state.stage == Stage.PRD_REVIEWING
    assert state.stage_status == StageStatus.FAILED

    reason = "接受终审阻断风险，先生成SDD"
    state = workflow.override_prd_review(state.project_id, reason)

    assert state.stage == Stage.SDD_CONFIRMING
    assert state.stage_status == StageStatus.WAITING_USER
    assert any(
        approval.kind == "prd_review_override"
        and approval.artifact_version == state.artifact_versions["prd"]
        for approval in state.approvals
    )

    state = workflow.submit_user_input(state.project_id, "下一步")
    sdd = repository.get_latest_artifact(state.project_id, ArtifactType.SDD)

    assert state.stage == Stage.COMPLETED
    assert sdd.metadata_json["prdReviewOverridden"] is True
    assert (
        sdd.metadata_json["prdReviewVersion"]
        == state.artifact_versions["prd-review"]
    )


def test_regenerate_sdd_creates_new_artifact_version(
    workflow: WorkflowEngine,
    repository: SQLAlchemyRepository,
    fake_executor: FakeTaskExecutor,
) -> None:
    state = advance_to_product_type_confirmation(workflow)
    state = workflow.submit_user_input(state.project_id, "下一步")
    state = workflow.submit_user_input(state.project_id, "下一步")

    assert state.stage == Stage.COMPLETED
    assert state.artifact_versions["sdd"] == 1

    state = workflow.regenerate_sdd(state.project_id)
    latest = repository.get_latest_artifact(state.project_id, ArtifactType.SDD)

    assert state.stage == Stage.COMPLETED
    assert state.stage_status == StageStatus.COMPLETED
    assert state.artifact_versions["sdd"] == 2
    assert latest.version == 2
    assert "# 工作流" in latest.content
    assert fake_executor.generate_sdd_calls == 2


def test_rollback_from_sdd_confirmation_to_prd_revision(
    workflow: WorkflowEngine,
    repository: SQLAlchemyRepository,
    fake_executor: FakeTaskExecutor,
) -> None:
    state = advance_to_product_type_confirmation(workflow)
    state = workflow.submit_user_input(state.project_id, "下一步")

    assert state.stage == Stage.SDD_CONFIRMING
    assert state.artifact_versions["prd"] == 2

    feedback = "补充PRD中的异常恢复说明"
    state = workflow.rollback(state.project_id, Stage.PRD_REVISING, feedback)
    prd = repository.get_latest_artifact(state.project_id, ArtifactType.PRD)
    stored = repository.get_project(state.project_id)

    assert state.stage == Stage.SDD_CONFIRMING
    assert state.stage_status == StageStatus.WAITING_USER
    assert prd.version == 3
    assert fake_executor.review_calls == 3
    assert "sdd" not in state.artifact_versions
    assert any(
        source.text == feedback
        for source in stored.requirement_spec.source_inputs
    )


def test_rollback_from_sdd_confirmation_to_product_type(
    workflow: WorkflowEngine,
) -> None:
    state = advance_to_product_type_confirmation(workflow)
    state = workflow.submit_user_input(state.project_id, "下一步")

    assert state.stage == Stage.SDD_CONFIRMING
    assert any(approval.kind == "product_type" for approval in state.approvals)

    state = workflow.rollback(
        state.project_id,
        Stage.PRD_TYPE_CONFIRMING,
        "产品类型需要重新判断",
    )

    assert state.stage == Stage.PRD_TYPE_CONFIRMING
    assert state.stage_status == StageStatus.WAITING_USER
    assert state.product_type is not None
    assert state.product_type.confirmed is False
    assert all(approval.kind != "product_type" for approval in state.approvals)
    assert "prd" not in state.artifact_versions


def test_illegal_rollback_is_rejected(workflow: WorkflowEngine) -> None:
    state = workflow.create_project("做一个产品")

    with pytest.raises(WorkflowGateError, match="不支持回退"):
        workflow.rollback(state.project_id, Stage.PRD_REVISING, "不能跳阶段")


def test_empty_requirement_is_rejected(workflow: WorkflowEngine) -> None:
    with pytest.raises(ValueError, match="不能为空"):
        workflow.create_project("   ")


def test_blocking_issue_cannot_be_waived(
    workflow: WorkflowEngine,
) -> None:
    state = workflow.create_project("做一个产品")
    state = workflow.submit_user_input(state.project_id, "覆盖完整五阶段")
    state = workflow.submit_user_input(state.project_id, "下一步")
    with pytest.raises(WorkflowGateError, match="不能豁免"):
        workflow.submit_user_input(state.project_id, "豁免 L-001: 暂时不处理")
