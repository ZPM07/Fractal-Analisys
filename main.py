import uvicorn
import logging
from src.utils.config import CONFIG

# Configure logging
logging.basicConfig(
    level=CONFIG.LOGGING_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        logger.info(f"Starting Lacunarity Analysis API")
        logger.info(f"Configuration:")
        logger.info(f"  Host: {CONFIG.API_HOST}")
        logger.info(f"  Port: {CONFIG.API_PORT}")
        logger.info(f"  Workers: {CONFIG.API_WORKERS}")
        logger.info(f"  Max Concurrent Calculations: {CONFIG.MAX_CONCURRENT_CALCULATIONS}")
        logger.info(f"  Logging Level: {CONFIG.LOGGING_LEVEL}")
        
        uvicorn.run(
            app="src.api:app",
            host=CONFIG.API_HOST,
            port=CONFIG.API_PORT,
            reload=False,
            workers=CONFIG.API_WORKERS,
            log_level=CONFIG.LOGGING_LEVEL.lower(),
        )
    except Exception as e:
        logger.error(f"Failed to start API: {e}", exc_info=True)
        raise
    finally:
        logger.info("API service stopped")