from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str | None = None
    test_database_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_provider: str | None = None
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    llm_timeout_seconds: int = Field(default=120, ge=1, le=600)
    llm_native_structured_output: bool | None = None
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    worker_poll_seconds: float = Field(default=1.0, ge=0.1, le=30)
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)
    database_read_timeout_seconds: int = Field(default=30, ge=1, le=600)
    # Deprecated compatibility settings. Prefer the provider-neutral LLM_* names.
    openai_api_key: str | None = None
    openai_model: str | None = None
    max_prd_revision_rounds: int = Field(default=3, ge=1, le=10)
    project_root: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[2]
    )
    upload_dir: Path = Path("uploads")
    upload_max_bytes: int = Field(default=20 * 1024 * 1024, ge=1)
    upload_max_files_per_project: int = Field(default=8, ge=1, le=50)

    @property
    def skill_root(self) -> Path:
        return self.project_root / "skills"

    @property
    def resolved_upload_dir(self) -> Path:
        if self.upload_dir.is_absolute():
            return self.upload_dir
        return self.project_root / self.upload_dir

    @property
    def resolved_llm_model(self) -> str | None:
        model = self.llm_model or self.openai_model
        if not model:
            return model
        if self.llm_provider:
            prefix = f"{self.llm_provider}/"
            return model.removeprefix(prefix)
        if "/" in model:
            return model
        if self.openai_model and not self.llm_model:
            return f"openai/{model}"
        return model

    @property
    def resolved_llm_api_key(self) -> str | None:
        return self.llm_api_key or self.openai_api_key

    def require_llm(self) -> None:
        model = self.resolved_llm_model
        if not model:
            raise ValueError("缺少环境变量：LLM_MODEL")
        if "/" not in model and not self.llm_provider:
            raise ValueError(
                "LLM_MODEL必须使用 provider/model 格式，"
                "或同时设置 LLM_PROVIDER"
            )

    @field_validator(
        "llm_model",
        "llm_api_key",
        "llm_base_url",
        "llm_provider",
        "openai_api_key",
        "openai_model",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("llm_native_structured_output", mode="before")
    @classmethod
    def normalize_optional_bool(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("llm_base_url")
    @classmethod
    def require_http_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("LLM_BASE_URL必须是有效的HTTP(S)地址")
        return value.rstrip("/")

    @field_validator("database_url", "test_database_url")
    @classmethod
    def require_supported_database_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        validate_database_url(normalized)
        return normalized

    @field_validator("test_database_url")
    @classmethod
    def require_test_database_suffix(cls, value: str | None) -> str | None:
        if value is None:
            return None
        validate_test_database_url(value)
        return value

    @model_validator(mode="after")
    def require_separate_databases(self) -> Settings:
        if self.database_url and self.test_database_url:
            validate_database_pair(self.database_url, self.test_database_url)
        if self.api_host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("MVP API只允许监听localhost")
        return self


def validate_mysql_url(value: str) -> str:
    url = make_url(value)
    if url.get_backend_name() != "mysql" or url.drivername != "mysql+pymysql":
        raise ValueError("数据库连接必须使用 mysql+pymysql")
    if url.query.get("charset") != "utf8mb4":
        raise ValueError("MySQL连接必须包含 charset=utf8mb4")
    return value


def validate_sqlite_url(value: str) -> str:
    url = make_url(value)
    if url.get_backend_name() != "sqlite" or url.drivername not in {
        "sqlite",
        "sqlite+pysqlite",
    }:
        raise ValueError("SQLite连接必须使用 sqlite 或 sqlite+pysqlite")
    if not url.database:
        raise ValueError("SQLite连接必须指定数据库文件路径")
    return value


def validate_database_url(value: str) -> str:
    backend = make_url(value).get_backend_name()
    if backend == "mysql":
        return validate_mysql_url(value)
    if backend == "sqlite":
        return validate_sqlite_url(value)
    raise ValueError("数据库仅支持 SQLite 或 mysql+pymysql")


def validate_test_database_url(value: str) -> str:
    validate_database_url(value)
    url = make_url(value)
    database = url.database or ""
    if url.get_backend_name() == "mysql" and not database.endswith("_test"):
        raise ValueError("MySQL测试数据库名称必须以 _test 结尾")
    if url.get_backend_name() == "sqlite":
        filename = Path(database).name
        if filename != ":memory:" and not Path(filename).stem.endswith("_test"):
            raise ValueError("SQLite测试数据库文件名必须以 _test 结尾")
    return value


def validate_database_pair(database_url: str, test_database_url: str) -> None:
    validate_database_url(database_url)
    validate_test_database_url(test_database_url)
    production = make_url(database_url)
    test = make_url(test_database_url)
    if production.get_backend_name() != test.get_backend_name():
        raise ValueError("DATABASE_URL 与 TEST_DATABASE_URL 必须使用相同数据库类型")
    if production.get_backend_name() == "mysql":
        production_target = (
            production.host,
            production.port or 3306,
            production.database,
        )
        test_target = (test.host, test.port or 3306, test.database)
    else:
        production_target = (Path(production.database or "").resolve(),)
        test_target = (Path(test.database or "").resolve(),)
    if production_target == test_target:
        raise ValueError("DATABASE_URL 与 TEST_DATABASE_URL 必须使用不同数据库")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
