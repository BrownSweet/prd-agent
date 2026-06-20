from __future__ import annotations

import re
from collections.abc import Callable

from crewai.flow import Flow, start
from pydantic import PrivateAttr

from prd_agent.gates import (
    WorkflowGateError,
    assert_logic_ready,
    assert_structure_ready,
    structure_readiness_errors,
    transition,
)
from prd_agent.models import (
    Approval,
    ArtifactType,
    AuditEvent,
    ClarificationQuestion,
    ItemStatus,
    ProjectState,
    Severity,
    SourceInput,
    Stage,
    StageStatus,
    reconcile_logic_issues,
    reconcile_questions,
)
from prd_agent.repositories import ArtifactNotFoundError, SQLAlchemyRepository
from prd_agent.tasks import TaskExecutor

NEXT_COMMANDS = {"下一步", "next", "确认", "confirm"}
RETRY_COMMANDS = {"重试", "retry"}
WAIVE_PATTERN = re.compile(
    r"^(?:豁免|waive)\s+(L-\d{3})(?:\s*[:：]\s*(.+))?$", re.IGNORECASE
)
STAGE_ORDER = [
    Stage.STRUCTURING,
    Stage.LOGIC_VALIDATING,
    Stage.PRD_TYPE_CONFIRMING,
    Stage.PRD_GENERATING,
    Stage.PRD_REVIEWING,
    Stage.PRD_REVISING,
    Stage.SDD_CONFIRMING,
    Stage.SDD_GENERATING,
    Stage.COMPLETED,
]
ROLLBACK_TARGETS: dict[Stage, tuple[Stage, ...]] = {
    Stage.PRD_TYPE_CONFIRMING: (Stage.LOGIC_VALIDATING,),
    Stage.PRD_REVIEWING: (Stage.PRD_REVISING, Stage.LOGIC_VALIDATING),
    Stage.SDD_CONFIRMING: (
        Stage.PRD_REVISING,
        Stage.PRD_TYPE_CONFIRMING,
    ),
}


def rollback_targets_for(stage: Stage) -> tuple[Stage, ...]:
    return ROLLBACK_TARGETS.get(stage, ())


class WorkflowEngine:
    def __init__(
        self,
        repository: SQLAlchemyRepository,
        executor: TaskExecutor,
        max_prd_revision_rounds: int = 3,
        artifact_metadata: dict[str, object] | None = None,
    ):
        self.repository = repository
        self.executor = executor
        self.max_prd_revision_rounds = max_prd_revision_rounds
        self.artifact_metadata = artifact_metadata or {}

    def create_project(self, requirement: str) -> ProjectState:
        state = self.initialize_project(requirement)
        return run_flow(self, state.project_id)

    def initialize_project(
        self,
        requirement: str,
        llm_config_id: str | None = None,
    ) -> ProjectState:
        requirement = requirement.strip()
        if not requirement:
            raise ValueError("需求描述不能为空")
        state = ProjectState()
        state.requirement_spec.source_inputs.append(SourceInput(text=requirement))
        self.repository.create_project(state, llm_config_id=llm_config_id)
        self._persist_event(state, "project_created", "项目已创建")
        return state

    def submit_user_input(self, project_id: str, user_input: str) -> ProjectState:
        state = self.repository.get_project(project_id)
        text = user_input.strip()
        if not text:
            raise ValueError("输入不能为空")

        if state.stage_status == StageStatus.FAILED:
            if self._failed_prd_review_needs_revision(state):
                if text.casefold() not in RETRY_COMMANDS:
                    state.pending_feedback = text
                    state.requirement_spec.source_inputs.append(SourceInput(text=text))
                transition(state, Stage.PRD_REVISING)
                self._persist_event(
                    state,
                    "prd_revision_requested",
                    "用户请求根据终审失败结果修订PRD",
                )
                return run_flow(self, project_id)
            if text.casefold() not in RETRY_COMMANDS:
                raise WorkflowGateError(["当前阶段失败，请输入“重试”"])
            state.stage_status = StageStatus.RUNNING
            self._persist_event(state, "stage_retry", "用户请求重试当前阶段")
            return run_flow(self, project_id)

        if state.stage_status != StageStatus.WAITING_USER:
            raise WorkflowGateError(["当前阶段不接受用户输入"])

        command = text.casefold()
        if state.stage == Stage.STRUCTURING:
            if command in NEXT_COMMANDS:
                assert_structure_ready(state)
                self._approve(state, "requirement_structure")
                transition(state, Stage.LOGIC_VALIDATING)
                self._persist_event(
                    state, "stage_transition", "需求结构化确认，进入逻辑校验"
                )
                return run_flow(self, project_id)
            return self._continue_with_feedback(state, text)

        if state.stage == Stage.LOGIC_VALIDATING:
            waive = WAIVE_PATTERN.match(text)
            if waive:
                self._waive_logic_issue(state, waive.group(1).upper(), waive.group(2))
                return state
            if command in NEXT_COMMANDS:
                assert_logic_ready(state)
                self._approve(state, "logic_validation")
                transition(state, Stage.PRD_TYPE_CONFIRMING)
                self._persist_event(
                    state, "stage_transition", "逻辑校验确认，进入产品类型识别"
                )
                return run_flow(self, project_id)
            return self._continue_with_feedback(state, text)

        if state.stage == Stage.PRD_TYPE_CONFIRMING:
            if command in NEXT_COMMANDS:
                if not state.product_type:
                    raise WorkflowGateError(["尚未生成产品类型识别结果"])
                state.product_type.confirmed = True
                self._approve(state, "product_type")
                transition(state, Stage.PRD_GENERATING)
                self._persist_event(
                    state, "stage_transition", "产品类型确认，开始生成PRD"
                )
                return run_flow(self, project_id)
            return self._continue_with_feedback(state, text)

        if state.stage == Stage.SDD_CONFIRMING:
            if command not in NEXT_COMMANDS:
                raise WorkflowGateError(["输入“下一步”确认生成SDD"])
            prd_version = state.artifact_versions.get(str(ArtifactType.PRD))
            self._approve(state, "sdd_generation", prd_version)
            transition(state, Stage.SDD_GENERATING)
            self._persist_event(state, "stage_transition", "用户确认生成SDD")
            return run_flow(self, project_id)

        raise WorkflowGateError([f"阶段 {state.stage} 不接受交互输入"])

    def advance(self, project_id: str) -> ProjectState:
        state = self.repository.get_project(project_id)
        if state.stage_status == StageStatus.WAITING_USER:
            return state
        if state.stage == Stage.COMPLETED:
            return state

        handlers: dict[Stage, Callable[[ProjectState], bool]] = {
            Stage.STRUCTURING: self._run_structuring,
            Stage.LOGIC_VALIDATING: self._run_logic_validation,
            Stage.PRD_TYPE_CONFIRMING: self._run_product_type_identification,
            Stage.PRD_GENERATING: self._run_prd_generation,
            Stage.PRD_REVIEWING: self._run_prd_review,
            Stage.PRD_REVISING: self._run_prd_revision,
            Stage.SDD_GENERATING: self._run_sdd_generation,
        }

        try:
            for _ in range(20):
                handler = handlers.get(state.stage)
                if not handler:
                    return state
                should_continue = handler(state)
                if not should_continue:
                    return state
            raise RuntimeError("自动阶段执行超过20步，已停止以避免无限循环")
        except Exception as exc:
            state.stage_status = StageStatus.FAILED
            self._persist_event(
                state,
                "stage_failed",
                f"阶段执行失败：{exc}",
                {"errorType": type(exc).__name__},
            )
            raise

    def rollback(
        self,
        project_id: str,
        target_stage: Stage,
        feedback: str | None = None,
    ) -> ProjectState:
        state = self.repository.get_project(project_id)
        if state.stage == Stage.COMPLETED:
            raise WorkflowGateError(["已完成项目暂不支持回退"])
        if state.stage_status not in {
            StageStatus.WAITING_USER,
            StageStatus.FAILED,
        }:
            raise WorkflowGateError(["当前阶段正在运行，不能回退"])
        if target_stage not in rollback_targets_for(state.stage):
            raise WorkflowGateError(
                [f"不支持回退：{state.stage} → {target_stage}"]
            )

        source_stage = state.stage
        text = (feedback or "").strip()
        if text:
            state.pending_feedback = text
            state.requirement_spec.source_inputs.append(SourceInput(text=text))
        else:
            state.pending_feedback = None

        self._clear_downstream_state(state, target_stage)
        state.stage = target_stage
        state.stage_status = StageStatus.RUNNING
        self._persist_event(
            state,
            "stage_rolled_back",
            f"阶段已回退：{source_stage} → {target_stage}",
            {
                "from": str(source_stage),
                "to": str(target_stage),
                "feedback": text,
            },
        )
        return run_flow(self, project_id)

    def override_prd_review(self, project_id: str, reason: str) -> ProjectState:
        state = self.repository.get_project(project_id)
        text = reason.strip()
        if not text:
            raise WorkflowGateError(["强行同意必须填写理由"])
        if (
            state.stage != Stage.PRD_REVIEWING
            or state.stage_status != StageStatus.FAILED
        ):
            raise WorkflowGateError(["只有终审失败时才能强行同意"])

        try:
            prd = self.repository.get_latest_artifact(
                state.project_id,
                ArtifactType.PRD,
            )
            review = self.repository.get_latest_artifact(
                state.project_id,
                ArtifactType.PRD_REVIEW,
            )
        except ArtifactNotFoundError as exc:
            raise WorkflowGateError(["没有可强行同意的PRD终审结果"]) from exc

        if review.metadata_json.get("passed") is not False:
            raise WorkflowGateError(["只有未通过的PRD终审才能强行同意"])
        if review.metadata_json.get("prdVersion") != prd.version:
            raise WorkflowGateError(["终审报告与最新PRD版本不一致"])

        self._approve(state, "prd_review_override", prd.version)
        transition(state, Stage.SDD_CONFIRMING, StageStatus.WAITING_USER)
        self._persist_event(
            state,
            "prd_review_overridden",
            "用户强行同意未通过的PRD终审，进入SDD确认",
            {
                "reason": text,
                "prdVersion": prd.version,
                "reviewVersion": review.version,
            },
        )
        return state

    def regenerate_sdd(self, project_id: str) -> ProjectState:
        state = self.repository.get_project(project_id)
        if (
            state.stage != Stage.COMPLETED
            or state.stage_status != StageStatus.COMPLETED
        ):
            raise WorkflowGateError(["只有已完成项目才能重新生成SDD"])
        if str(ArtifactType.SDD) not in state.artifact_versions:
            raise WorkflowGateError(["项目尚未生成SDD"])

        artifact = self._save_sdd_artifact(state)
        state.artifact_versions[str(ArtifactType.SDD)] = artifact.version
        self._persist_event(
            state,
            "sdd_regenerated",
            f"SDD已重新生成为v{artifact.version}",
        )
        return state

    def _continue_with_feedback(
        self, state: ProjectState, feedback: str
    ) -> ProjectState:
        state.pending_feedback = feedback
        state.requirement_spec.source_inputs.append(SourceInput(text=feedback))
        state.stage_status = StageStatus.RUNNING
        state.round_number += 1
        self._persist_event(state, "user_feedback", "已接收用户补充信息")
        return run_flow(self, state.project_id)

    def _run_structuring(self, state: ProjectState) -> bool:
        source_inputs = list(state.requirement_spec.source_inputs)
        feedback = state.pending_feedback
        result = self.executor.structure_requirements(state)
        result.requirement_spec.source_inputs = source_inputs
        state.requirement_spec = result.requirement_spec
        state.questions = reconcile_questions(
            state.questions,
            result.questions,
            result.resolved_question_ids,
            feedback,
        )
        gate_errors = structure_readiness_errors(state)
        if gate_errors and not any(
            item.status == ItemStatus.OPEN for item in state.questions
        ):
            state.questions = reconcile_questions(
                state.questions,
                self._questions_for_structure_errors(gate_errors),
                [],
                None,
            )
        state.pending_feedback = None
        state.stage_status = StageStatus.WAITING_USER
        self.repository.save_project(state)
        self.repository.save_requirement_snapshot(state)
        self._persist_event(
            state,
            "requirements_structured",
            "需求结构化本轮完成，等待用户补充或确认",
            {"openQuestions": self._open_question_count(state)},
        )
        return False

    @staticmethod
    def _questions_for_structure_errors(
        errors: list[str],
    ) -> list[ClarificationQuestion]:
        questions: list[ClarificationQuestion] = []
        seen: set[str] = set()
        for error in errors:
            if error == "仍存在未解决的澄清问题" or error in seen:
                continue
            seen.add(error)
            if "交互逻辑" in error or "交互定义" in error:
                question_type = "交互逻辑"
                description = (
                    "请补充关键功能的交互逻辑：触发方式、系统反馈、"
                    "页面或接口流转分别是什么？"
                )
                importance = "决定是否能进入7维逻辑校验"
            elif "操作影响" in error:
                question_type = "操作影响"
                description = (
                    "请补充关键操作的操作影响：会影响哪些数据、模块、"
                    "用户侧表现，以及立即还是延迟生效？"
                )
                importance = "用于追踪操作后果并生成后续PRD/SDD"
            elif "数据来源" in error:
                question_type = "数据来源"
                description = "请补充数据来源；如果没有外部数据，也请明确说明为“无”及原因。"
                importance = "决定字段、接口和数据模型边界"
            elif "依赖关系" in error:
                question_type = "依赖关系"
                description = "请补充模块、功能或外部服务之间的依赖关系；如果没有依赖，也请明确说明。"
                importance = "决定后续状态流转和删除影响"
            elif "模块" in error or "功能点" in error:
                question_type = "模块"
                description = "请补充完整模块和每个模块下的核心功能点。"
                importance = "决定产品范围"
            else:
                question_type = "结构化缺口"
                description = f"请补充：{error}"
                importance = "当前缺口会阻止进入下一阶段"
            questions.append(
                ClarificationQuestion(
                    question_id="Q-999",
                    question_type=question_type,
                    description=description,
                    importance=importance,
                )
            )
        return questions

    def _run_logic_validation(self, state: ProjectState) -> bool:
        source_inputs = list(state.requirement_spec.source_inputs)
        feedback = state.pending_feedback
        result = self.executor.validate_logic(state)
        result.requirement_spec.source_inputs = source_inputs
        state.requirement_spec = result.requirement_spec
        state.logic_issues = reconcile_logic_issues(
            state.logic_issues,
            result.issues,
            result.resolved_issue_ids,
            feedback,
        )
        state.pending_feedback = None
        state.stage_status = StageStatus.WAITING_USER
        self.repository.save_project(state)
        self.repository.save_requirement_snapshot(state)
        self._persist_event(
            state,
            "logic_validated",
            "七维逻辑扫描完成，等待用户处理或确认",
            {"openIssues": self._open_issue_count(state)},
        )
        return False

    def _run_product_type_identification(self, state: ProjectState) -> bool:
        result = self.executor.identify_product_type(state)
        result.product_type.confirmed = False
        state.product_type = result.product_type
        state.pending_feedback = None
        state.stage_status = StageStatus.WAITING_USER
        self._persist_event(
            state,
            "product_type_identified",
            "产品类型识别完成，等待用户确认",
            {
                "primary": str(result.product_type.primary),
                "secondary": [str(item) for item in result.product_type.secondary],
            },
        )
        return False

    def _run_prd_generation(self, state: ProjectState) -> bool:
        result = self.executor.write_prd(state)
        state.requirement_spec.business_rules = result.business_rules
        artifact = self.repository.save_artifact(
            state.project_id,
            ArtifactType.PRD,
            result.markdown,
            {
                "reviewRound": state.review_round,
                "revisionCount": 0,
                **self.artifact_metadata,
            },
        )
        state.artifact_versions[str(ArtifactType.PRD)] = artifact.version
        transition(state, Stage.PRD_REVIEWING)
        self._persist_event(
            state,
            "prd_generated",
            f"PRD v{artifact.version} 已生成，自动进入终审",
        )
        return True

    def _run_prd_review(self, state: ProjectState) -> bool:
        prd = self.repository.get_latest_artifact(
            state.project_id, ArtifactType.PRD
        )
        result = self.executor.review_prd(state, prd.content)
        state.review_round += 1
        review = self.repository.save_artifact(
            state.project_id,
            ArtifactType.PRD_REVIEW,
            result.report_markdown,
            {
                "passed": result.passed,
                "issues": [
                    issue.model_dump(mode="json", by_alias=True)
                    for issue in result.issues
                ],
                "prdVersion": prd.version,
                **self.artifact_metadata,
            },
        )
        state.artifact_versions[str(ArtifactType.PRD_REVIEW)] = review.version

        if result.passed:
            transition(state, Stage.SDD_CONFIRMING, StageStatus.WAITING_USER)
            self._persist_event(
                state,
                "prd_review_passed",
                f"PRD v{prd.version} 终审通过，等待生成SDD确认",
            )
            return False

        revision_count = self._prd_revision_count(prd.metadata_json, prd.version)
        if revision_count >= self.max_prd_revision_rounds:
            state.stage_status = StageStatus.FAILED
            self._persist_event(
                state,
                "prd_review_limit_reached",
                f"PRD已修订{revision_count}轮，仍未通过终审",
            )
            return False

        transition(state, Stage.PRD_REVISING)
        self._persist_event(
            state,
            "prd_review_failed",
            f"PRD v{prd.version} 未通过终审，自动进入修订",
        )
        return True

    def _run_prd_revision(self, state: ProjectState) -> bool:
        prd = self.repository.get_latest_artifact(
            state.project_id, ArtifactType.PRD
        )
        review = self.repository.get_latest_artifact(
            state.project_id, ArtifactType.PRD_REVIEW
        )
        revision_count = self._prd_revision_count(
            prd.metadata_json,
            prd.version,
        )
        result = self.executor.revise_prd(state, prd.content, review.content)
        state.requirement_spec.business_rules = result.business_rules
        artifact = self.repository.save_artifact(
            state.project_id,
            ArtifactType.PRD,
            result.markdown,
            {
                "revisedFrom": prd.version,
                "reviewVersion": review.version,
                "revisionCount": revision_count + 1,
                **self.artifact_metadata,
            },
        )
        state.artifact_versions[str(ArtifactType.PRD)] = artifact.version
        transition(state, Stage.PRD_REVIEWING)
        self._persist_event(
            state,
            "prd_revised",
            f"PRD已修订为v{artifact.version}，自动重新终审",
        )
        return True

    def _failed_prd_review_needs_revision(self, state: ProjectState) -> bool:
        if state.stage != Stage.PRD_REVIEWING:
            return False
        try:
            review = self.repository.get_latest_artifact(
                state.project_id,
                ArtifactType.PRD_REVIEW,
            )
        except ArtifactNotFoundError:
            return False
        return review.metadata_json.get("passed") is False

    def _run_sdd_generation(self, state: ProjectState) -> bool:
        prd = self.repository.get_latest_artifact(
            state.project_id, ArtifactType.PRD
        )
        review = self.repository.get_latest_artifact(
            state.project_id, ArtifactType.PRD_REVIEW
        )
        review_overridden = self._has_prd_review_override(state, prd.version)
        if not review.metadata_json.get("passed") and not review_overridden:
            raise WorkflowGateError(["只有终审通过的PRD才能生成SDD"])
        artifact = self._save_sdd_artifact(state, prd, review, review_overridden)
        state.artifact_versions[str(ArtifactType.SDD)] = artifact.version
        transition(state, Stage.COMPLETED, StageStatus.COMPLETED)
        self._persist_event(
            state,
            "sdd_generated",
            f"SDD v{artifact.version} 已生成，流程完成",
        )
        return False

    def _save_sdd_artifact(
        self,
        state: ProjectState,
        prd=None,
        review=None,
        review_overridden=None,
    ):
        prd = prd or self.repository.get_latest_artifact(
            state.project_id, ArtifactType.PRD
        )
        review = review or self.repository.get_latest_artifact(
            state.project_id, ArtifactType.PRD_REVIEW
        )
        if review_overridden is None:
            review_overridden = self._has_prd_review_override(state, prd.version)
        if not review.metadata_json.get("passed") and not review_overridden:
            raise WorkflowGateError(["只有终审通过的PRD才能生成SDD"])

        result = self.executor.generate_sdd(state, prd.content)
        return self.repository.save_artifact(
            state.project_id,
            ArtifactType.SDD,
            self._sdd_markdown(result),
            {
                "prdVersion": prd.version,
                "prdReviewVersion": review.version,
                "prdReviewOverridden": review_overridden,
                "technicalDefaults": result.technical_defaults,
                **self.artifact_metadata,
            },
        )

    @staticmethod
    def _sdd_markdown(result) -> str:
        if not result.modules:
            return result.markdown
        parts = []
        for module in result.modules:
            body = module.markdown.strip()
            if body.startswith("# "):
                parts.append(body)
            else:
                parts.append(f"# {module.name}\n\n{body}")
        return "\n\n".join(parts)

    @staticmethod
    def _has_prd_review_override(state: ProjectState, prd_version: int) -> bool:
        return any(
            approval.kind == "prd_review_override"
            and approval.artifact_version == prd_version
            for approval in state.approvals
        )

    def _approve(
        self, state: ProjectState, kind: str, artifact_version: int | None = None
    ) -> None:
        state.approvals.append(
            Approval(
                kind=kind,
                stage=state.stage,
                artifact_version=artifact_version,
            )
        )

    def _clear_downstream_state(
        self,
        state: ProjectState,
        target_stage: Stage,
    ) -> None:
        target_index = STAGE_ORDER.index(target_stage)
        state.approvals = [
            approval
            for approval in state.approvals
            if STAGE_ORDER.index(approval.stage) < target_index
        ]
        if target_stage in {
            Stage.LOGIC_VALIDATING,
            Stage.PRD_TYPE_CONFIRMING,
        }:
            state.product_type = None
            state.review_round = 0
            for artifact_type in (
                ArtifactType.PRD,
                ArtifactType.PRD_REVIEW,
                ArtifactType.SDD,
            ):
                state.artifact_versions.pop(str(artifact_type), None)
        if target_stage == Stage.PRD_REVISING:
            state.artifact_versions.pop(str(ArtifactType.SDD), None)

    @staticmethod
    def _prd_revision_count(metadata: dict[str, object], version: int) -> int:
        value = metadata.get("revisionCount")
        if isinstance(value, int):
            return value
        return max(version - 1, 0)

    def _waive_logic_issue(
        self, state: ProjectState, issue_id: str, reason: str | None
    ) -> None:
        issue = next(
            (item for item in state.logic_issues if item.issue_id == issue_id),
            None,
        )
        if not issue:
            raise WorkflowGateError([f"逻辑问题不存在：{issue_id}"])
        if issue.severity == Severity.BLOCKING:
            raise WorkflowGateError(["阻断问题不能豁免，必须解决"])
        if not reason:
            raise WorkflowGateError(["豁免重要问题必须提供原因"])
        issue.status = ItemStatus.WAIVED
        issue.resolution = reason
        self._persist_event(
            state,
            "logic_issue_waived",
            f"{issue_id} 已由用户明确豁免",
            {"reason": reason},
        )

    def _persist_event(
        self,
        state: ProjectState,
        event_type: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        event = AuditEvent(
            event_type=event_type,
            stage=state.stage,
            message=message,
            details=details or {},
        )
        state.audit_events = [*state.audit_events[-49:], event]
        self.repository.save_project(state)
        self.repository.add_event(state.project_id, event)

    @staticmethod
    def _open_question_count(state: ProjectState) -> int:
        return sum(item.status == ItemStatus.OPEN for item in state.questions)

    @staticmethod
    def _open_issue_count(state: ProjectState) -> int:
        return sum(item.status == ItemStatus.OPEN for item in state.logic_issues)


class ProductDeliveryFlow(Flow[ProjectState]):
    """Thin CrewAI Flow wrapper; MySQL remains the source of truth."""

    _skip_auto_memory = True
    _engine: WorkflowEngine = PrivateAttr()
    _project_id: str = PrivateAttr()

    def __init__(self, engine: WorkflowEngine, project_id: str):
        super().__init__(tracing=False, suppress_flow_events=True)
        self._engine = engine
        self._project_id = project_id

    @start()
    def run_current_stage(self) -> ProjectState:
        return self._engine.advance(self._project_id)


def run_flow(engine: WorkflowEngine, project_id: str) -> ProjectState:
    result = ProductDeliveryFlow(engine, project_id).kickoff()
    if isinstance(result, ProjectState):
        return result
    return engine.repository.get_project(project_id)
