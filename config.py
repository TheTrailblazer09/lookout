"""Configuration. Everything environment-dependent lives here, nowhere else."""
import os
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent

universe_df = pd.read_csv(BASE_DIR / "universe_200.csv")

class Config:
    # --- security --------------------------------------------------------
    # MUST be set in the environment before anything leaves your laptop.
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    JWT_ALGORITHM = "HS256"
    JWT_TTL_HOURS = 24 * 7          # a week; nobody re-logs-in mid-demo
    PASSWORD_MIN_LENGTH = 8
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

    # --- storage ---------------------------------------------------------
    DATA_DIR = BASE_DIR / "data"
    DB_PATH = DATA_DIR / "lookout.duckdb"
    NEWS_CACHE_DIR = DATA_DIR / "news_cache"

    # --- the clock -------------------------------------------------------
    AS_OF_OVERRIDE = os.getenv("AS_OF_OVERRIDE") or None
 
    @staticmethod
    def default_as_of() -> str:
        from datetime import date
        return Config.AS_OF_OVERRIDE or str(date.today())
    
    # The demo runs as if it were this date. Every read defaults to it.
    # Set to None in production to mean "real today".
    DEFAULT_AS_OF = "2025-01-27"
    REPLAY_START = "2025-01-13"
    REPLAY_END = "2025-02-14"

    # --- universe --------------------------------------------------------
    MARKET_TICKER = "SPY"
    UNIVERSE = universe_df["ticker"].tolist()
    DEMO_PORTFOLIO_ID = "demo"

    # --- local models ----------------------------------------------------
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    LLM_FAST = os.getenv("LLM_FAST", "qwen3.5:9b")     # per-alert text
    LLM_DEEP = os.getenv("LLM_DEEP", "qwen3.8:27b")    # daily summary
    # Per model call. The first call after a model is pulled also loads it
    # into memory, which is the slow one; later calls are quick.
    LLM_TIMEOUT = 20
    # Alerts are generated inside a web request, so the whole narration
    # step gets a ceiling. Anything past it is written on the next load
    # rather than holding the page open.
    NARRATION_BUDGET_SECONDS = 45
    FINBERT_MODEL = "ProsusAI/finbert"

    # --- data sources ----------------------------------------------------
    ALPHAVANTAGE_KEY = os.getenv("ALPHAVANTAGE_KEY", "ZM2CM3TRXYAONK5O")
    FRED_KEY = os.getenv("FRED_KEY", "a9e6a7e44e8bfb7eebbf75adcece0882 ")
    SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "Lookout HackGT team@example.com")

    # --- method constants (kept here so results are reproducible) --------
    EST_WINDOW = 120        # trading days used to fit the market model
    EST_GAP = 10            # gap between estimation window and the event
    WINDOW_COMPANY = 5      # days 0..+5 for earnings / company news
    WINDOW_MACRO = 1        # days 0..+1 for Fed / CPI
    SHRINK_STRENGTH = 8.0   # prior weight, in pseudo-events
    BOOTSTRAP_N = 500
    PURGE_DAYS = 8          # calendar days between train and test splits


class DevConfig(Config):
    DEBUG = True


class TestConfig(Config):
    DEBUG = True
    DB_PATH = Config.DATA_DIR / "test.duckdb"


CONFIGS = {"dev": DevConfig, "test": TestConfig, "default": DevConfig}


def get_config(name: str | None = None) -> type[Config]:
    return CONFIGS.get(name or os.getenv("LOOKOUT_ENV", "default"), DevConfig)