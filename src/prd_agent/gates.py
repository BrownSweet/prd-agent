from __future__ import annotations

from collections.abc import Iterable

from prd_agent.models import (
    ItemStatus,
    ProjectState,
    Severity,
    Stage,
    StageStatus,
)


class WorkflowGateError(ValueError):
    def __init__(self, errors: Iterable[str]):
        self.errors = list(errors)
        super().__init__("；".join(self.errors))


ALLOWED_TRANSITIONS: dict[Stage, set[Stage]] = {
    Stage.STRUCTURING: {Stage.LOGIC_VALIDATING},
    Stage.LOGIC_VALIDATING: {Stage.PRD_TYPE_CONFIRMING},
    Stage.PRD_TYPE_CONFIRMING: {Stage.PRD_GENERATING},
    Stage.PRD_GENERATING: {Stage.PRD_REVIEWING},
    Stage.PRD_REVIEWING: {Stage.PRD_REVISING, Stage.SDD_CONFIRMING},
    Stage.PRD_REVISING: {Stage.PRD_REVIEWING},
    Stage.SDD_CONFIRMING: {Stage.SDD_GENERATING},
    Stage.SDD_GENERATING: {Stage.COMPLETED},
    Stage.COMPLETED: set(),
}


def structure_readiness_errors(state: ProjectState) -> list[str]:
    spec = state.requirement_spec
    errors: list[str] = []
    checks = (
        (spec.completeness.modules_complete, "模块尚未完整"),
        (spec.completeness.data_sources_clear, "数据来源尚未明确"),
        (spec.completeness.interactions_clear, "交互逻辑尚未明确"),
        (spec.completeness.impacts_traceable, "操作影响尚不可追溯"),
        (spec.completeness.dependencies_clear, "依赖关系尚未明确"),
    )
    errors.extend(message for passed, message in checks if not passed)

    if not spec.modules or any(not module.features for module in spec.modules):
        errors.append("至少需要一个包含功能点的模块")
    if not spec.data_sources:
        errors.append("需要显式声明数据来源，确实无数据时也应记录为“无”")
    if not spec.interactions:
        errors.append("至少需要一条交互定义")
    if not spec.operation_impacts:
        errors.append("至少需要一条操作影响定义")
    if not spec.dependencies:
        errors.append("需要显式声明依赖关系，确实无依赖时也应记录为“无”")
    if any(item.status == ItemStatus.OPEN for item in state.questions):
        errors.append("仍存在未解决的澄清问题")
    return errors


def logic_readiness_errors(state: ProjectState) -> list[str]:
    errors: list[str] = []
    blocking = [
        item
        for item in state.logic_issues
        if item.status == ItemStatus.OPEN and item.severity == Severity.BLOCKING
    ]
    important = [
        item
        for item in state.logic_issues
        if item.status == ItemStatus.OPEN and item.severity == Severity.IMPORTANT
    ]
    if blocking:
        errors.append(f"仍有 {len(blocking)} 个阻断问题未解决")
    if important:
        errors.append(f"仍有 {len(important)} 个重要问题未解决或豁免")
    return errors


def assert_structure_ready(state: ProjectState) -> None:
    errors = structure_readiness_errors(state)
    if errors:
        raise WorkflowGateError(errors)


def assert_logic_ready(state: ProjectState) -> None:
    errors = logic_readiness_errors(state)
    if errors:
        raise WorkflowGateError(errors)


def transition(
    state: ProjectState,
    target: Stage,
    status: StageStatus = StageStatus.RUNNING,
) -> None:
    if target not in ALLOWED_TRANSITIONS[state.stage]:
        raise WorkflowGateError([f"非法阶段迁移：{state.stage} → {target}"])
    state.stage = target
    state.stage_status = status
    state.pending_feedback = None

