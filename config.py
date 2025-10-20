import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import List

load_dotenv()

class Settings(BaseModel):
    telegram_api_id: int = Field(default_factory=lambda: int(os.getenv("TELEGRAM_API_ID", "0")))
    telegram_api_hash: str = os.getenv("TELEGRAM_API_HASH", "")
    telegram_phone: str = os.getenv("TELEGRAM_PHONE", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    target_channels: List[str] = Field(
        default_factory=lambda: [c.strip() for c in os.getenv("TARGET_CHANNELS", "").split(",") if c.strip()]
    )
    interest_keywords: List[str] = Field(
        default_factory=lambda: [k.strip().lower() for k in os.getenv("INTEREST_KEYWORDS", "").split(",") if k.strip()]
    )
    days_lookback: int = int(os.getenv("DAYS_LOOKBACK", "7"))
    lead_confidence_threshold: float = float(os.getenv("LEAD_CONFIDENCE_THRESHOLD", "0.6"))

settings = Settings()