from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, Field

ROOT = Path(__file__).parent.parent.parent
WORKSPACE = Path("./workspace")
SCRIPTS = ROOT / "src" / "harness" / "scripts"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_deployment: str
    
    workspace: Path = WORKSPACE
    scripts: Path = SCRIPTS
    
    max_turns: int = Field(20, ge=1, le=100)
    timeout: int = Field(60, ge=1, le=600)
    
    price_in: float = 0.05
    price_out: float = 0.40
    
    @field_validator("workspace")
    @classmethod
    def absolutize(cls, v:Path) -> Path:
        return v if v.is_absolute() else (ROOT/v).resolve()
    
    @field_validator("azure_openai_endpoint")
    @classmethod
    def check(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("endpoint must start with https://")
        return v.rstrip("/")
    
settings = Settings()