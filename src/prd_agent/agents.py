from __future__ import annotations

from typing import Any

from crewai import Agent, LLM
from crewai.skills.parser import load_skill_metadata, load_skill_resources

from prd_agent.settings import Settings


class AgentFactory:
    def __init__(self, settings: Settings):
        settings.require_llm()
        self.settings = settings
        llm_options: dict[str, Any] = {
            "model": settings.resolved_llm_model or "",
            "temperature": settings.llm_temperature,
            "timeout": settings.llm_timeout_seconds,
        }
        if settings.resolved_llm_api_key:
            llm_options["api_key"] = settings.resolved_llm_api_key
        if settings.llm_base_url:
            llm_options["base_url"] = settings.llm_base_url
        if settings.llm_provider:
            llm_options["provider"] = settings.llm_provider
        self.llm = LLM(**llm_options)

    @property
    def supports_native_structured_output(self) -> bool:
        configured = self.settings.llm_native_structured_output
        if configured is not None:
            return configured
        return self.llm.provider not in {
            "deepseek",
            "ollama",
            "ollama_chat",
            "hosted_vllm",
        }

    def product_analyst(self, skill_name: str) -> Agent:
        return self._agent(
            role="产品需求分析专家",
            goal="将产品需求转化为完整、可追溯且逻辑闭环的结构化规格",
            backstory=(
                "你擅长识别需求中的事实、假设和缺口。你保持稳定编号，"
                "不会用主观推断掩盖未确认信息。"
            ),
            skill_name=skill_name,
        )

    def prd_writer(self) -> Agent:
        return self._agent(
            role="PRD撰写专家",
            goal="基于已确认的结构化需求生成可审查、可实施的PRD",
            backstory=(
                "你熟悉管理后台、C端、API、数据产品、平台和硬件产品。"
                "你只写已确认的业务事实，并明确记录技术默认值。"
            ),
            skill_name="write-prd",
        )

    def prd_reviewer(self) -> Agent:
        return self._agent(
            role="PRD独立终审专家",
            goal="独立发现PRD中的逻辑矛盾、流程断点和场景遗漏",
            backstory=(
                "你与PRD作者职责隔离，只输出审查结论和问题，"
                "绝不静默改写被审文档。"
            ),
            skill_name="review-prd",
        )

    def solution_architect(self) -> Agent:
        return self._agent(
            role="SDD技术规范专家",
            goal="将终审通过的PRD转换为可直接开发的技术契约",
            backstory=(
                "你重视接口、数据、状态、事务、错误和验收标准的一致性。"
                "你不会增加PRD中不存在的业务能力。"
            ),
            skill_name="generate-sdd",
        )

    def _agent(
        self,
        role: str,
        goal: str,
        backstory: str,
        skill_name: str,
    ) -> Agent:
        skill_path = self.settings.skill_root / skill_name
        if not skill_path.exists():
            raise FileNotFoundError(f"Skill不存在：{skill_path}")
        skill = load_skill_resources(load_skill_metadata(skill_path))
        return Agent(
            role=role,
            goal=goal,
            backstory=backstory,
            llm=self.llm,
            skills=[skill],
            allow_delegation=False,
            max_iter=12,
            respect_context_window=True,
            verbose=False,
        )
