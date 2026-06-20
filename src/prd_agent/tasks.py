from __future__ import annotations

import json
import re
from typing import Any, Protocol, TypeVar, cast

from crewai import Crew, Process, Task
from pydantic import BaseModel

from prd_agent.agents import AgentFactory
from prd_agent.gates import structure_readiness_errors
from prd_agent.models import (
    LogicValidationResult,
    PrdResult,
    PrdReviewResult,
    ProductTypeResult,
    ProjectState,
    RequirementStructureResult,
    SddResult,
)

OutputModel = TypeVar("OutputModel", bound=BaseModel)


class TaskExecutor(Protocol):
    def structure_requirements(
        self, state: ProjectState
    ) -> RequirementStructureResult: ...

    def validate_logic(self, state: ProjectState) -> LogicValidationResult: ...

    def identify_product_type(self, state: ProjectState) -> ProductTypeResult: ...

    def write_prd(self, state: ProjectState) -> PrdResult: ...

    def review_prd(self, state: ProjectState, prd: str) -> PrdReviewResult: ...

    def revise_prd(
        self, state: ProjectState, prd: str, review: str
    ) -> PrdResult: ...

    def generate_sdd(self, state: ProjectState, prd: str) -> SddResult: ...


def _json_context(state: ProjectState) -> str:
    return state.model_dump_json(indent=2, by_alias=True)


def _parse_raw(model: type[OutputModel], raw: str) -> OutputModel:
    cleaned = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    return model.model_validate_json(cleaned)


def _validate_identifiers(output: BaseModel) -> None:
    for field_name, id_field in (
        ("questions", "question_id"),
        ("issues", "issue_id"),
        ("business_rules", "rule_id"),
    ):
        items = getattr(output, field_name, None)
        if items is None:
            continue
        identifiers = [getattr(item, id_field) for item in items]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"{field_name} 中存在重复编号")


def _validate_document_sections(output: BaseModel) -> None:
    if isinstance(output, RequirementStructureResult):
        errors = structure_readiness_errors(
            ProjectState(
                requirement_spec=output.requirement_spec,
                questions=output.questions,
            )
        )
        if errors and not output.questions:
            raise ValueError(
                "结构化需求仍不完整但没有追问："
                + "；".join(errors)
            )
        if errors and any(
            marker in output.summary_markdown
            for marker in ("信息充分", "进入步骤2", "下一步")
        ):
            raise ValueError(
                "结构化需求仍不完整，summaryMarkdown不得提示进入下一步"
            )
    if isinstance(output, PrdResult):
        headings = [
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
        missing = [item for item in headings if f"## {item}" not in output.markdown]
        if missing:
            raise ValueError(f"PRD缺少章节：{', '.join(missing)}")
    if isinstance(output, PrdReviewResult):
        required = {
            "逻辑准确性",
            "流程闭环性",
            "场景覆盖度",
            "交互统一性",
            "用户使用逻辑",
        }
        actual = {item.dimension for item in output.dimensions}
        if actual != required or len(output.dimensions) != len(required):
            raise ValueError("终审必须且只能覆盖五个规定维度")
    if isinstance(output, SddResult):
        headings = [
            "功能契约",
            "页面结构与组件树",
            "数据模型定义",
            "API接口定义",
            "数据库表设计",
            "核心交互流程",
            "测试验收标准",
            "技术决策与约束",
        ]
        for module in output.modules:
            missing = [
                item for item in headings if f"## {item}" not in module.markdown
            ]
            if missing:
                raise ValueError(
                    f"SDD模块“{module.name}”缺少章节：{', '.join(missing)}"
                )


def output_guardrail(model: type[OutputModel]):
    def validate(result: Any) -> tuple[bool, Any]:
        try:
            parsed = getattr(result, "pydantic", None)
            if not isinstance(parsed, model):
                parsed = _parse_raw(model, result.raw)
            _validate_identifiers(parsed)
            _validate_document_sections(parsed)
            return True, result.raw
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return False, f"结构化输出校验失败：{exc}"

    return validate


class CrewAITaskExecutor:
    def __init__(self, agents: AgentFactory):
        self.agents = agents

    def structure_requirements(
        self, state: ProjectState
    ) -> RequirementStructureResult:
        description = f"""
对下面的项目状态进行本轮需求结构化。整合所有sourceInputs和pendingFeedback，
输出完整RequirementSpec，而不是只输出增量。

规则：
1. 覆盖模块、数据来源、交互、操作影响、依赖关系。
2. 未经用户确认的内容放入assumptions，不能伪装为事实。
3. 仍不明确的问题放入questions；避免重复已有问题并保持稳定编号。
4. 只有五项都有明确证据且无待澄清问题时，completeness对应字段才可为true。
5. 确实不存在的数据来源或依赖，也要显式记录“无”及理由。
6. summaryMarkdown使用规定的中文表格格式。
7. requirementSpec.sourceInputs由系统维护，返回空数组，不得改写原始输入。

项目状态：
{_json_context(state)}
"""
        return self._execute(
            agent=self.agents.product_analyst("structure-requirements"),
            description=description,
            expected_output="完整的 RequirementStructureResult JSON",
            output_model=RequirementStructureResult,
        )

    def validate_logic(self, state: ProjectState) -> LogicValidationResult:
        description = f"""
对下面的完整需求执行新一轮七维逻辑扫描：依赖关系、状态流转、边界条件、
操作影响、逆向操作、交互一致性、异常场景。

规则：
1. 输出当前仍存在的问题，不重复已解决问题。
2. 严重程度只能是blocking、important、suggestion。
3. 根据pendingFeedback判断上一轮问题是否解决，resolvedIssueIds列出已解决编号。
4. 将用户对逻辑问题的答案同步纳入完整requirementSpec。
5. summaryMarkdown必须含本轮发现、已修复回顾和数量统计。
6. 不得决定是否进入下一阶段。
7. requirementSpec.sourceInputs由系统维护，返回空数组，不得改写原始输入。

项目状态：
{_json_context(state)}
"""
        return self._execute(
            agent=self.agents.product_analyst("validate-requirement-logic"),
            description=description,
            expected_output="完整的 LogicValidationResult JSON",
            output_model=LogicValidationResult,
        )

    def identify_product_type(self, state: ProjectState) -> ProductTypeResult:
        description = f"""
根据已确认需求识别产品类型。类型可为A管理后台、B C端应用、C API/服务、
D数据产品、E中台/平台、F硬件/嵌入式。

选择一个primary，可选择多个secondary。结合pendingFeedback修正识别结果。
只做类型识别，不生成PRD；confirmed必须为false，等待代码层用户确认。

项目状态：
{_json_context(state)}
"""
        return self._execute(
            agent=self.agents.prd_writer(),
            description=description,
            expected_output="完整的 ProductTypeResult JSON",
            output_model=ProductTypeResult,
        )

    def write_prd(self, state: ProjectState) -> PrdResult:
        description = f"""
根据下面已确认的结构化需求和产品类型生成完整中文PRD。

强制要求：
1. 依次使用九个二级章节：文档信息、修订历史、项目背景与目标、
   核心名词定义、功能需求总览、详细功能需求、非功能需求、
   全局交互规范、附录。
2. 每个功能包含字段规格表、交互步骤表、唯一R-XXX业务规则和
   Loading/Empty/Error/Data页面状态。
3. 非功能要求按主产品类型侧重，并兼顾次产品类型。
4. 不添加需求中没有的业务逻辑；不确定项明确标记待确认。
5. businessRules返回PRD使用的完整规则清单。

项目状态：
{_json_context(state)}
"""
        return self._execute(
            agent=self.agents.prd_writer(),
            description=description,
            expected_output="章节齐全的 PrdResult JSON",
            output_model=PrdResult,
            quality_guardrail=(
                "检查PRD是否忠实于输入需求、九章齐全、规则可执行且没有臆造业务。"
                "只判断文档质量，不得决定工作流阶段。"
            ),
        )

    def review_prd(self, state: ProjectState, prd: str) -> PrdReviewResult:
        description = f"""
独立终审下面的PRD。只输出审查报告，禁止改写或返回新的PRD正文。

必须检查五个维度：逻辑准确性、流程闭环性、场景覆盖度、交互统一性、
用户使用逻辑。可选建议标记为非阻断。任何失败维度或阻断问题都必须使
passed=false。

结构化需求：
{_json_context(state)}

待审PRD：
{prd}
"""
        return self._execute(
            agent=self.agents.prd_reviewer(),
            description=description,
            expected_output="只包含审查结论的 PrdReviewResult JSON",
            output_model=PrdReviewResult,
        )

    def revise_prd(
        self, state: ProjectState, prd: str, review: str
    ) -> PrdResult:
        description = f"""
根据终审报告修订PRD。保留已确认且未被问题影响的内容，只修复审查指出的
缺陷。不得删除需求、降低约束或引入新业务功能。返回完整PRD，不返回diff。

修订要求：
- 逐条修复终审报告中的所有阻断问题。
- 对非阻断建议，如果它导致任一审查维度不通过，也必须纳入修订。
- 如果结构化上下文中的 pendingFeedback 有用户修订意见，必须纳入修订。
- 修订后的PRD必须能看出与当前PRD的实质差异，禁止原文无变化返回。
- 在修订历史或相关章节中体现本轮修复点，便于再次终审追踪。

结构化需求：
{_json_context(state)}

当前PRD：
{prd}

终审报告：
{review}
"""
        return self._execute(
            agent=self.agents.prd_writer(),
            description=description,
            expected_output="修订后的完整 PrdResult JSON",
            output_model=PrdResult,
            quality_guardrail=(
                "检查修订稿是否逐项修复终审问题，同时没有删除已确认需求或增加新业务。"
                "只判断文档质量，不得决定工作流阶段。"
            ),
        )

    def generate_sdd(self, state: ProjectState, prd: str) -> SddResult:
        description = f"""
将下面终审通过的PRD转换为按模块拆分的SDD。

每个模块严格包含八个二级章节：功能契约、页面结构与组件树、数据模型定义、
API接口定义、数据库表设计、核心交互流程、测试验收标准、技术决策与约束。
不适用章节明确写“本模块不适用”及理由，不能臆造页面或数据库。
PRD未指定技术栈时可使用默认技术栈，但必须把每项默认选择列入
technicalDefaults。不得添加PRD中不存在的业务逻辑。

已确认项目状态：
{_json_context(state)}

终审通过PRD：
{prd}
"""
        return self._execute(
            agent=self.agents.solution_architect(),
            description=description,
            expected_output="模块化且章节齐全的 SddResult JSON",
            output_model=SddResult,
            quality_guardrail=(
                "检查SDD是否可直接实施、内部一致、严格基于PRD，并显式列出技术默认值。"
                "只判断文档质量，不得决定工作流阶段。"
            ),
        )

    def _execute(
        self,
        agent: Any,
        description: str,
        expected_output: str,
        output_model: type[OutputModel],
        quality_guardrail: str | None = None,
    ) -> OutputModel:
        task = self._create_task(
            agent=agent,
            description=description,
            expected_output=expected_output,
            output_model=output_model,
            quality_guardrail=quality_guardrail,
        )
        result = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            memory=False,
            cache=False,
            verbose=False,
        ).kickoff()
        parsed = result.pydantic
        if not isinstance(parsed, output_model):
            parsed = _parse_raw(output_model, result.raw)
        _validate_identifiers(parsed)
        _validate_document_sections(parsed)
        return cast(OutputModel, parsed)

    def _create_task(
        self,
        agent: Any,
        description: str,
        expected_output: str,
        output_model: type[OutputModel],
        quality_guardrail: str | None = None,
    ) -> Task:
        native_structured_output = (
            self.agents.supports_native_structured_output
        )
        guardrails: list[Any] = [output_guardrail(output_model)]
        if quality_guardrail:
            if native_structured_output:
                guardrails.append(quality_guardrail)
            else:
                description += (
                    "\n\n提交最终JSON前执行以下质量自检：\n"
                    f"{quality_guardrail}"
                )
        if not native_structured_output:
            schema = json.dumps(
                output_model.model_json_schema(by_alias=True),
                ensure_ascii=False,
            )
            description += f"""

输出协议：
1. 最终答案只能是一个JSON对象，不要使用Markdown代码块。
2. JSON必须符合下面的JSON Schema。
3. 不得输出解释、前言或后记。

JSON Schema：
{schema}
"""
        return Task(
            description=description,
            expected_output=expected_output,
            agent=agent,
            output_pydantic=(
                output_model if native_structured_output else None
            ),
            guardrails=guardrails,
            guardrail_max_retries=2,
        )
