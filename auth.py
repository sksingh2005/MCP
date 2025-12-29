"""
Authentication module for MCP Banking Server.
Provides API key validation middleware for FastAPI.
"""

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from typing import Optional

from database import validate_api_key

# API Key header configuration
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_api_key(api_key: Optional[str] = Security(API_KEY_HEADER)) -> str:
    """
    Dependency for validating API key from X-API-Key header.
    
    Raises:
        HTTPException: 401 if API key is missing or invalid
    
    Returns:
        The validated API key
    """
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key. Include 'X-API-Key' header.",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    if not validate_api_key(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    return api_key


def verify_api_key_simple(api_key: Optional[str]) -> bool:
    """
    Simple API key verification for MCP tools.
    
    Args:
        api_key: The API key to validate
        
    Returns:
        True if valid, False otherwise
    """
    if api_key is None:
        return False
    return validate_api_key(api_key)
