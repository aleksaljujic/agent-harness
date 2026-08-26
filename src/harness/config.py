from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, Field

ROOT = Path(__file__).parent.parent.parent
WORKSPACE = Path("./workspace")
SCRIPTS = ROOT / "src" / "harness" / "scripts"

MODEL_PRICING = {
    "gpt-5.6-sol":   (5.00, 30.00),
    "gpt-5.6-terra": (2.00, 12.00),
    "gpt-5.6-luna":  (0.20, 1.20),
    "gpt-5.4-nano":  (0.20, 1.25),
    "gpt-5-nano":    (0.05, 0.40),
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
    
    enabled_tools: list[str] = Field(default_factory=lambda: ["bash", "search", "str_replace"])
    
    @field_validator("workspace")
    @classmethod
    def absolutize(cls, v:Path) -> Path:
        return v if v.is_absolute() else (ROOT/v).resolve()
    
    @field_validator("endpoint")
    @classmethod
    def check(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("endpoint must start with https://")
        return v.rstrip("/")
    
settings = Settings()