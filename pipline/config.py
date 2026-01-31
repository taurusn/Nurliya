"""
Configuration management for Nurliya Pipeline.
Supports GCP Secret Manager with fallback to environment variables.
"""

import os
import logging
from dotenv import load_dotenv
from functools import lru_cache

load_dotenv()

# Get logger (will use logging_config if imported, otherwise basic)
logger = logging.getLogger(__name__)

# GCP Secret Manager settings
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
USE_SECRET_MANAGER = os.getenv("USE_SECRET_MANAGER", "false").lower() == "true"

# Secret Manager client (lazy loaded)
_secret_manager_client = None
_secret_manager_available = None


def _get_secret_manager_client():
    """Lazy load Secret Manager client."""
    global _secret_manager_client, _secret_manager_available

    if _secret_manager_available is False:
        return None

    if _secret_manager_client is None:
        try:
            from google.cloud import secretmanager
            _secret_manager_client = secretmanager.SecretManagerServiceClient()
            _secret_manager_available = True
            logger.info("GCP Secret Manager client initialized")
        except ImportError:
            logger.debug("google-cloud-secret-manager not installed, using environment variables")
            _secret_manager_available = False
            return None
        except Exception as e:
            logger.warning(f"Failed to initialize Secret Manager client: {e}")
            _secret_manager_available = False
            return None

    return _secret_manager_client


@lru_cache(maxsize=128)
def get_secret(secret_name: str, default: str = "") -> str:
    """
    Get a secret value with fallback chain:
    1. GCP Secret Manager (if enabled and available)
    2. Environment variable
    3. Default value

    Args:
        secret_name: Name of the secret (used as both Secret Manager ID and env var name)
        default: Default value if secret not found anywhere

    Returns:
        Secret value from the first available source
    """
    # Try Secret Manager first if enabled
    if USE_SECRET_MANAGER and GCP_PROJECT_ID:
        client = _get_secret_manager_client()
        if client:
            try:
                # Build the resource name
                name = f"projects/{GCP_PROJECT_ID}/secrets/{secret_name}/versions/latest"
                response = client.access_secret_version(request={"name": name})
                secret_value = response.payload.data.decode("UTF-8")
                logger.debug(f"Loaded '{secret_name}' from Secret Manager")
                return secret_value
            except Exception as e:
                logger.debug(f"Secret '{secret_name}' not found in Secret Manager: {e}")
                # Fall through to environment variable

    # Fall back to environment variable
    env_value = os.getenv(secret_name)
    if env_value is not None:
        return env_value

    # Return default
    return default


def get_secret_int(secret_name: str, default: int) -> int:
    """Get a secret as an integer."""
    value = get_secret(secret_name, str(default))
    try:
        return int(value)
    except ValueError:
        logger.warning(f"Invalid integer value for '{secret_name}', using default: {default}")
        return default


# Database
DATABASE_URL = get_secret("DATABASE_URL", "postgresql://nurliya:nurliya123@localhost:5432/nurliya")

# RabbitMQ
RABBITMQ_URL = get_secret("RABBITMQ_URL", "amqp://nurliya:nurliya123@localhost:5672/")

# Queue settings (non-sensitive, keep as env vars)
QUEUE_NAME = os.getenv("QUEUE_NAME", "review_analysis")
DLQ_NAME = os.getenv("DLQ_NAME", "review_analysis_dlq")
PREFETCH_COUNT = int(os.getenv("PREFETCH_COUNT", "1"))

# Scraper settings
SCRAPER_API_URL = get_secret("SCRAPER_API_URL", "http://localhost:8080")
SCRAPER_POLL_INTERVAL = get_secret_int("SCRAPER_POLL_INTERVAL", 5)

# Results directory (non-sensitive)
RESULTS_DIR = os.getenv("RESULTS_DIR", "../results")

# LLM settings (named VLLM for backwards compatibility)
VLLM_BASE_URL = get_secret("VLLM_BASE_URL", "http://localhost:8080/v1")
VLLM_API_KEY = get_secret("VLLM_API_KEY", "")
VLLM_MODEL = get_secret("VLLM_MODEL", "gemini-2.0-flash")

# API settings (non-sensitive)
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# SMTP settings (sensitive)
SMTP_HOST = get_secret("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = get_secret_int("SMTP_PORT", 587)
SMTP_USER = get_secret("SMTP_USER", "")
SMTP_PASSWORD = get_secret("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = get_secret("SMTP_FROM_EMAIL", "")

# Deprecated - kept for backwards compatibility
GEMINI_API_KEY = get_secret("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash-lite"
