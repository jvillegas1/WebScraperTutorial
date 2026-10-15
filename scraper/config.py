"""
Configuración centralizada del Web Scraper de Inmuebles.
Soporta dos tiers: Venezuela (nacional) y Argentina (mercado dinámico).
"""

import os
from pathlib import Path
from dotenv import load_dotenv

from .regions import REGIONS, get_region_config, get_active_sources, list_regions

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "inmuebles.db"

DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

DEBUG = os.getenv("DEBUG", "false").lower() == "true"
DEFAULT_REGION = "venezuela"

# Compatibilidad con código legacy (Venezuela por defecto)
DEFAULT_REGION = "venezuela"
_VE_CONFIG = get_region_config("venezuela")

ACTIVE_SOURCES = _VE_CONFIG["active_sources"]
SCRAPING_CONFIG = _VE_CONFIG["scraping"]
OPPORTUNITY_RULES = _VE_CONFIG["opportunity_rules"]
PORTAL_URLS = _VE_CONFIG["portal_urls"]

SCHEDULER_CONFIG = {
    "scraping_interval_hours": _VE_CONFIG["scraping_interval_hours"],
    "opportunity_check_interval_hours": _VE_CONFIG["opportunity_check_interval_hours"],
    "cleanup_interval_days": 7,
}

EMAIL_CONFIG = {
    "enabled": os.getenv("EMAIL_ENABLED", "false").lower() == "true",
    "smtp_server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
    "smtp_port": int(os.getenv("SMTP_PORT", "587")),
    "smtp_user": os.getenv("SMTP_USER", ""),
    "smtp_password": os.getenv("SMTP_PASSWORD", ""),
    "from_email": os.getenv("FROM_EMAIL", ""),
    "to_emails": os.getenv("TO_EMAILS", "").split(",") if os.getenv("TO_EMAILS") else [],
}

TELEGRAM_CONFIG = {
    "enabled": os.getenv("TELEGRAM_ENABLED", "false").lower() == "true",
    "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
    "chat_ids": os.getenv("TELEGRAM_CHAT_IDS", "").split(",") if os.getenv("TELEGRAM_CHAT_IDS") else [],
}

ALERT_CONFIG = {
    "cooldown_hours": 168,
    "batch_threshold": 10,
    "batch_delay_minutes": 30,
}

LOGGING_CONFIG = {
    "level": "DEBUG" if DEBUG else "INFO",
    "format": "json",
    "max_file_size_mb": 10,
    "backup_count": 5,
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]
