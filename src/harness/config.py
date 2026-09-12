from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent.parent
WORKSPACE = ROOT / "workspace"
SCRIPTS = ROOT / "src" / "harness" / "scripts"

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class Price(NamedTuple):
    input: float   # USD per 1M input tokens
    output: float  # USD per 1M output tokens


MODEL_PRICING = {
    "gpt-5.4-nano": Price(0.20, 1.25),
    "gpt-5.4-mini": Price(0.75, 4.50),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    endpoint: str
    api_key: str
    model: str
    provider: str

    workspace: Path = WORKSPACE
    scripts: Path = SCRIPTS

    max_turns: int = Field(20, ge=1, le=100)
    timeout: int = Field(60, ge=1, le=600)

    reasoning_effort: str | None = None  # None | minimal | low | medium | high

    enabled_tools: list[str] = Field(
        default_factory=lambda: ["bash", "search", "str_replace", "read_file", "find_file", "run_tests"]
    )

    @field_validator("workspace", "scripts")
    @classmethod
    def absolutize(cls, v: Path) -> Path:
        return v if v.is_absolute() else (ROOT / v).resolve()

    @field_validator("endpoint")
    @classmethod
    def normalize_endpoint(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in ("https", "http"):
            raise ValueError("endpoint must start with https:// (or http:// for a local host)")
        if parsed.scheme == "http" and parsed.hostname not in LOCAL_HOSTS:
            raise ValueError(f"endpoint may only use http:// for {sorted(LOCAL_HOSTS)}, not {parsed.hostname!r}")
        return v.rstrip("/")

    @field_validator("reasoning_effort")
    @classmethod
    def known_effort(cls, v):
        if v in (None, "", "none"):
            return None
        allowed = {"minimal", "low", "medium", "high"}
        if v not in allowed:
            raise ValueError(f"reasoning_effort must be one of {sorted(allowed)} or None, got {v!r}")
        return v

    @field_validator("enabled_tools")
    @classmethod
    def known_tools(cls, v: list[str]) -> list[str]:
        from harness.tools import REGISTRY

        unknown = [t for t in v if t not in REGISTRY]
        if unknown:
            raise ValueError(f"unknown tools {unknown}; known: {sorted(REGISTRY)}")
        return v

    @model_validator(mode="after")
    def priced_model(self):
        if self.model not in MODEL_PRICING:
            raise ValueError(
                f"no pricing for model {self.model!r}; add it to MODEL_PRICING "
                f"(known: {sorted(MODEL_PRICING)})"
            )
        return self


settings = Settings()
