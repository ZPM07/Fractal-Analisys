import ctypes
import tempfile
import asyncio
import logging
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
import numpy as np
from pydantic import BaseModel

from src.utils.paths import PATH_TO_CPP_LIB
from src.utils.config import CONFIG
from src.calculations.lacunarity.lacunarity import Lacunarity

logging.basicConfig(
    level=CONFIG.LOGGING_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=CONFIG.API_TITLE,
    description="API for fractal lacunarity analysis",
    version=CONFIG.API_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SEMAPHORE = asyncio.Semaphore(CONFIG.MAX_CONCURRENT_CALCULATIONS)

logger.info(f"API initialized with max {CONFIG.MAX_CONCURRENT_CALCULATIONS} concurrent calculations")


class LacunarityResponse(BaseModel):
    """Response model for lacunarity calculation"""
    status: str
    message: str
    data: Optional[dict] = None


def cleanup_temp_file(file_path: str):
    """Background task to clean up temporary files"""
    try:
        Path(file_path).unlink(missing_ok=True)
        logger.debug(f"Cleaned up temporary file: {file_path}")
    except Exception as e:
        logger.error(f"Error cleaning up temp file {file_path}: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    logger.debug("Health check requested")
    return {"status": "ok", "message": "Lacunarity API is running"}


@app.post("/analyze")
async def analyze_lacunarity(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    number_of_slices: int = Query(100, ge=1, description="Number of slices for calculation"),
    connectivity: int = Query(4, description="Connectivity method (4 or 8)"),
    box_counting: int = Query(2, description="Box counting method (1 or 2)"),
) -> LacunarityResponse:
    """
    Analyze lacunarity from an uploaded file
    
    Args:
        file: Text file with matrix data
        number_of_slices: Number of slices for calculation (default: 100)
        connectivity: Connectivity method - 4 or 8 (default: 4)
        box_counting: Box counting method - 1 or 2 (default: 2)
        background_tasks: Background tasks for cleanup
    
    Returns:
        LacunarityResponse with calculation results
    
    Raises:
        HTTPException: If parameters are invalid or calculation fails
    """
    logger.info(
        f"Lacunarity analysis requested: slices={number_of_slices}, "
        f"connectivity={connectivity}, box_counting={box_counting}"
    )
    
    if connectivity not in [4, 8]:
        logger.warning(f"Invalid connectivity value: {connectivity}")
        raise HTTPException(status_code=400, detail="Connectivity must be 4 or 8")
    if box_counting not in [1, 2]:
        logger.warning(f"Invalid box_counting value: {box_counting}")
        raise HTTPException(status_code=400, detail="Box counting must be 1 or 2")
    if number_of_slices <= 0:
        logger.warning(f"Invalid number_of_slices value: {number_of_slices}")
        raise HTTPException(status_code=400, detail="Number of slices must be positive")
    
    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", delete=False, suffix=".txt"
        ) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            temp_file_path = tmp_file.name
        
        logger.debug(f"Temporary file saved: {temp_file_path}")
        
        background_tasks.add_task(cleanup_temp_file, temp_file_path)
        
        logger.debug("Waiting for semaphore to acquire")
        async with SEMAPHORE:
            logger.debug("Semaphore acquired, starting calculation")
            results = await run_in_threadpool(
                _calculate_lacunarity,
                temp_file_path,
                number_of_slices,
                connectivity,
                box_counting,
            )
        
        logger.info("Lacunarity calculation completed successfully")
        return LacunarityResponse(
            status="success",
            message="Lacunarity calculation completed successfully",
            data=results,
        )
    
    except ValueError as e:
        logger.error(f"Invalid input data: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid input data: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Error during calculation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error during calculation: {str(e)}",
        )


def _calculate_lacunarity(
    file_path: str,
    number_of_slices: int,
    connectivity: int,
    box_counting: int,
) -> dict:
    """
    Internal function to calculate lacunarity (runs in thread pool)
    
    Args:
        file_path: Path to matrix data file
        number_of_slices: Number of slices for calculation
        connectivity: Connectivity method
        box_counting: Box counting method
    
    Returns:
        Dictionary with calculation results
    
    Raises:
        ValueError: If calculation fails
    """
    logger.info(f"Starting lacunarity calculation for file: {file_path}")
    
    try:
        # Load C++ library
        logger.debug(f"Loading C++ library from: {PATH_TO_CPP_LIB}")
        lib = ctypes.CDLL(PATH_TO_CPP_LIB)
        lacunarity_calc = Lacunarity(lib)
        logger.debug("C++ library loaded successfully")
        
        calc_ptr = None
        
        logger.debug("Executing lacunarity calculation")
        calc_ptr, results = lacunarity_calc.calc_all(
            file_path,
            number_of_slices=number_of_slices,
            connectivity=connectivity,
            box_counting=box_counting,
        )
        logger.debug("Calculation completed successfully")
        
        # Convert numpy arrays to lists for JSON serialization
        # Replace inf and nan with None for JSON compatibility
        def make_json_compatible(obj):
            if isinstance(obj, np.ndarray):
                arr = obj.tolist()
                # Replace inf and nan values
                def clean_value(val):
                    if isinstance(val, float):
                        if np.isinf(val) or np.isnan(val):
                            return None
                    elif isinstance(val, list):
                        return [clean_value(v) for v in val]
                    return val
                return clean_value(arr)
            return obj
        
        results_serializable = {
            key: make_json_compatible(value)
            for key, value in results.items()
        }
        logger.debug(f"Results serialized, fields: {list(results_serializable.keys())}")
        
        # Free memory
        if calc_ptr is not None:
            logger.debug("Freeing C++ memory")
            lib.memory_free(calc_ptr)
            logger.debug("Memory freed successfully")
        
        return results_serializable
    
    except Exception as e:
        logger.error(f"Calculation failed: {str(e)}", exc_info=True)
        raise ValueError(f"Calculation failed: {str(e)}")


@app.get("/info")
async def get_info():
    """Get information about the API and library"""
    logger.debug("Info endpoint requested")
    return {
        "api_name": CONFIG.API_TITLE,
        "version": CONFIG.API_VERSION,
        "library": "liblacunarity",
        "max_concurrent_calculations": CONFIG.MAX_CONCURRENT_CALCULATIONS,
        "supported_parameters": {
            "connectivity": [4, 8],
            "box_counting": [1, 2],
            "number_of_slices": "positive integer",
        },
    }
