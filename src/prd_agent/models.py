from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class Schema(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class Stage(StrEnum):
    STRUCTURING = "STRUCTURING"
    LOGIC_VALIDATING = "LOGIC_VALIDATING"
    PRD_TYPE_CONFIRMING = "PRD_TYPE_CONFIRMING"
    PRD_GENERATING = "PRD_GENERATING"
    PRD_REVIEWING = "PRD_REVIEWING"
    PRD_REVISING = "PRD_REVISING"
    SDD_CONFIRMING = "SDD_CONFIRMING"
    SDD_GENERATING = "SDD_GENERATING"
    COMPLETED = "COMPLETED"


class StageStatus(StrEnum):
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    FAILED = "failed"
    COMPLETED = "completed"


class ItemStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    WAIVED = "waived"


class Severity(StrEnum):
    BLOCKING = "blocking"
    IMPORTANT = "important"
    SUGGESTION = "suggestion"


class ProductTypeCode(StrEnum):
    ADMIN = "A"
    CONSUMER = "B"
    API = "C"
    DATA = "D"
    PLATFORM = "E"
    HARDWARE = "F"


class ArtifactType(StrEnum):
    PRD = "prd"
    PRD_REVIEW = "prd-review"
    SDD = "sdd"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobType(StrEnum):
    WORKFLOW = "workflow"
    LLM_TEST = "llm-test"
    API_WRITE = "api-write"


class SourceInput(Schema):
    text: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)


class RequirementFeature(Schema):
    name: str
    description: str
    data_source: str
    interaction_logic: str
    operation_impact: str
    dependencies: list[str] = Field(default_factory=list)


class RequirementModule(Schema):
    name: str
    description: str
    features: list[RequirementFeature] = Field(default_factory=list)


class DataSourceDefinition(Schema):
    name: str
    source_type: str
    owner: str
    freshness: str


class InteractionDefinition(Schema):
    trigger: str
    system_behavior: str
    feedback: str


class OperationImpact(Schema):
    operation: str
    affected_targets: list[str]
    timing: str
    reversible: bool


class DependencyDefinition(Schema):
    upstream: str
    downstream: str
    relationship: str
    deletion_impact: str


class RequirementStateDefinition(Schema):
    name: str
    entry_condition: str
    exit_condition: str


class BusinessRule(Schema):
    rule_id: str = Field(pattern=r"^R-\d{3}$")
    description: str


class CompletenessAssessment(Schema):
    modules_complete: bool = False
    data_sources_clear: bool = False
    interactions_clear: bool = False
    impacts_traceable: bool = False
    dependencies_clear: bool = False

    @property
    def is_complete(self) -> bool:
        return all(
            (
                self.modules_complete,
                self.data_sources_clear,
                self.interactions_clear,
                self.impacts_traceable,
                self.dependencies_clear,
            )
        )


class RequirementSpec(Schema):
    title: str = ""
    summary: str = ""
    modules: list[RequirementModule] = Field(default_factory=list)
    data_sources: list[DataSourceDefinition] = Field(default_factory=list)
    interactions: list[InteractionDefinition] = Field(default_factory=list)
    operation_impacts: list[OperationImpact] = Field(default_factory=list)
    dependencies: list[DependencyDefinition] = Field(default_factory=list)
    states: list[RequirementStateDefinition] = Field(default_factory=list)
    business_rules: list[BusinessRule] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    source_inputs: list[SourceInput] = Field(default_factory=list)
    completeness: CompletenessAssessment = Field(
        default_factory=CompletenessAssessment
    )


class ClarificationQuestion(Schema):
    question_id: str = Field(pattern=r"^Q-\d{3}$")
    question_type: str
    description: str
    importance: str
    status: ItemStatus = ItemStatus.OPEN
    answer: str | None = None

    @model_validator(mode="after")
    def closed_question_requires_answer(self) -> ClarificationQuestion:
        if self.status != ItemStatus.OPEN and not self.answer:
            raise ValueError("已关闭的澄清问题必须记录答案")
        return self


class LogicIssue(Schema):
    issue_id: str = Field(pattern=r"^L-\d{3}$")
    dimension: str
    description: str
    severity: Severity
    status: ItemStatus = ItemStatus.OPEN
    resolution: str | None = None

    @model_validator(mode="after")
    def closed_issue_requires_resolution(self) -> LogicIssue:
        if self.status != ItemStatus.OPEN and not self.resolution:
            raise ValueError("已关闭的逻辑问题必须记录解决方案或豁免原因")
        return self


class ProductTypeSelection(Schema):
    primary: ProductTypeCode
    secondary: list[ProductTypeCode] = Field(default_factory=list)
    matched_features: list[str]
    rationale: str
    confirmed: bool = False

    @model_validator(mode="after")
    def remove_primary_from_secondary(self) -> ProductTypeSelection:
        self.secondary = [item for item in self.secondary if item != self.primary]
        return self


class Approval(Schema):
    approval_id: str = Field(default_factory=lambda: str(uuid4()))
    kind: str
    stage: Stage
    artifact_version: int | None = None
    approved_at: datetime = Field(default_factory=utc_now)


class ArtifactVersion(Schema):
    artifact_type: ArtifactType
    version: int
    created_at: datetime = Field(default_factory=utc_now)


class AuditEvent(Schema):
    event_type: str
    stage: Stage
    message: str
    created_at: datetime = Field(default_factory=utc_now)
    details: dict[str, Any] = Field(default_factory=dict)


class ProjectState(Schema):
    project_id: str = Field(default_factory=lambda: str(uuid4()))
    stage: Stage = Stage.STRUCTURING
    stage_status: StageStatus = StageStatus.RUNNING
    round_number: int = 1
    review_round: int = 0
    requirement_spec: RequirementSpec = Field(default_factory=RequirementSpec)
    questions: list[ClarificationQuestion] = Field(default_factory=list)
    logic_issues: list[LogicIssue] = Field(default_factory=list)
    product_type: ProductTypeSelection | None = None
    approvals: list[Approval] = Field(default_factory=list)
    artifact_versions: dict[str, int] = Field(default_factory=dict)
    audit_events: list[AuditEvent] = Field(default_factory=list)
    pending_feedback: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


def _discard_generated_source_inputs(value: Any) -> Any:
    """Source inputs are owned by the workflow, never by model output."""
    if not isinstance(value, dict):
        return value
    result = dict(value)
    spec_key = (
        "requirementSpec"
        if "requirementSpec" in result
        else "requirement_spec"
    )
    spec = result.get(spec_key)
    if isinstance(spec, dict):
        trusted_spec = dict(spec)
        trusted_spec.pop("sourceInputs", None)
        trusted_spec.pop("source_inputs", None)
        result[spec_key] = trusted_spec
    return result


class RequirementStructureResult(Schema):
    requirement_spec: RequirementSpec
    questions: list[ClarificationQuestion] = Field(default_factory=list)
    resolved_question_ids: list[str] = Field(default_factory=list)
    summary_markdown: str

    @model_validator(mode="before")
    @classmethod
    def ignore_generated_source_inputs(cls, value: Any) -> Any:
        return _discard_generated_source_inputs(value)


class LogicValidationResult(Schema):
    requirement_spec: RequirementSpec
    issues: list[LogicIssue] = Field(default_factory=list)
    resolved_issue_ids: list[str] = Field(default_factory=list)
    summary_markdown: str

    @model_validator(mode="before")
    @classmethod
    def ignore_generated_source_inputs(cls, value: Any) -> Any:
        return _discard_generated_source_inputs(value)


class ProductTypeResult(Schema):
    product_type: ProductTypeSelection
    summary_markdown: str


class PrdResult(Schema):
    markdown: str
    business_rules: list[BusinessRule]


class ReviewDimension(Schema):
    dimension: str
    passed: bool
    explanation: str


class ReviewIssue(Schema):
    issue_id: str = Field(pattern=r"^L-\d{3}$")
    description: str
    blocking: bool
    suggestion_type: str


class PrdReviewResult(Schema):
    passed: bool
    dimensions: list[ReviewDimension]
    issues: list[ReviewIssue] = Field(default_factory=list)
    report_markdown: str

    @model_validator(mode="after")
    def passed_requires_clean_dimensions(self) -> PrdReviewResult:
        if self.passed and (
            any(not item.passed for item in self.dimensions)
            or any(item.blocking for item in self.issues)
        ):
            raise ValueError("终审通过时不能存在失败维度或阻断问题")
        return self


class SddModule(Schema):
    name: str
    markdown: str


class SddResult(Schema):
    markdown: str
    modules: list[SddModule]
    technical_defaults: list[str] = Field(default_factory=list)


def _canonical_text(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _next_identifier(prefix: str, used: set[str]) -> str:
    number = 1
    while f"{prefix}-{number:03d}" in used:
        number += 1
    identifier = f"{prefix}-{number:03d}"
    used.add(identifier)
    return identifier


def reconcile_questions(
    existing: list[ClarificationQuestion],
    incoming: list[ClarificationQuestion],
    resolved_ids: list[str],
    answer: str | None,
) -> list[ClarificationQuestion]:
    used = {item.question_id for item in existing}
    existing_by_text = {_canonical_text(item.description): item for item in existing}
    resolved = set(resolved_ids)
    merged: list[ClarificationQuestion] = []
    incoming_texts: set[str] = set()

    for item in incoming:
        key = _canonical_text(item.description)
        incoming_texts.add(key)
        previous = existing_by_text.get(key)
        if previous:
            item.question_id = previous.question_id
            if previous.status != ItemStatus.OPEN:
                item.status = previous.status
                item.answer = previous.answer
        else:
            item.question_id = _next_identifier("Q", used)
        merged.append(item)

    for previous in existing:
        key = _canonical_text(previous.description)
        if key in incoming_texts:
            continue
        if previous.question_id in resolved:
            previous.status = ItemStatus.RESOLVED
            previous.answer = answer or previous.answer
        merged.append(previous)

    return sorted(merged, key=lambda item: item.question_id)


def reconcile_logic_issues(
    existing: list[LogicIssue],
    incoming: list[LogicIssue],
    resolved_ids: list[str],
    resolution: str | None,
) -> list[LogicIssue]:
    used = {item.issue_id for item in existing}
    existing_by_text = {_canonical_text(item.description): item for item in existing}
    resolved = set(resolved_ids)
    merged: list[LogicIssue] = []
    incoming_texts: set[str] = set()

    for item in incoming:
        key = _canonical_text(item.description)
        incoming_texts.add(key)
        previous = existing_by_text.get(key)
        if previous:
            item.issue_id = previous.issue_id
            if previous.status != ItemStatus.OPEN:
                item.status = previous.status
                item.resolution = previous.resolution
        else:
            item.issue_id = _next_identifier("L", used)
        merged.append(item)

    for previous in existing:
        key = _canonical_text(previous.description)
        if key in incoming_texts:
            continue
        if previous.issue_id in resolved:
            previous.status = ItemStatus.RESOLVED
            previous.resolution = resolution or previous.resolution
        merged.append(previous)

    return sorted(merged, key=lambda item: item.issue_id)
