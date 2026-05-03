import os
from dotenv import load_dotenv

load_dotenv()

class CONFIG:

    # ---------- PROJECT ---------
    API_PORT = int(os.getenv("API_PORT", 8000))
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_WORKERS = int(os.getenv("API_WORKERS", 1))
    API_TITLE = os.getenv("API_TITLE", "Lacunarity Analysis API")
    API_VERSION = os.getenv("API_VERSION", "1.0.0")
    MAX_CONCURRENT_CALCULATIONS = int(os.getenv("MAX_CONCURRENT_CALCULATIONS", 3))
    LOGGING_LEVEL = os.getenv("LOGGING_LEVEL", "INFO")
