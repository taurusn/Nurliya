import os
from dotenv import load_dotenv

load_dotenv()

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://nurliya:nurliya123@localhost:5432/nurliya")

# RabbitMQ
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://nurliya:nurliya123@localhost:5672/")

# Queue settings
QUEUE_NAME = "review_analysis"
DLQ_NAME = "review_analysis_dlq"
PREFETCH_COUNT = 1

# Scraper settings
SCRAPER_API_URL = os.getenv("SCRAPER_API_URL", "http://localhost:8080")
SCRAPER_POLL_INTERVAL = int(os.getenv("SCRAPER_POLL_INTERVAL", "5"))

# Results directory
RESULTS_DIR = os.getenv("RESULTS_DIR", "../results")

# vLLM settings
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://206.168.83.147:8080/v1")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "token-sadnxai")
VLLM_MODEL = os.getenv("VLLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct")

# API settings
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# SMTP settings for email notifications
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")  # Gmail address
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")  # Gmail App Password
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "")  # Same as SMTP_USER typically

# Deprecated - kept for backwards compatibility
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.0-flash-lite"
