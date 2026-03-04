#!/usr/bin/env python3
"""
Direct test of login functionality.
"""

import sys
import traceback
sys.path.insert(0, '.')

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from src.multimodal_librarian.services.user_service import get_user_service
from src.multimodal_librarian.security.auth import get_auth_service, AuthenticationError
from src.multimodal_librarian.logging_config import configure_logging, get_logger
from datetime import timedelta

# Configure logging
configure_logging()
logger = get_logger(__name__)

app = FastAPI(title="Login Test")

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/login")
async def login(login_data: LoginRequest):
    """Test login endpoint."""
    try:
        logger.info(f"Login request: {login_data.username}")
        
        # Get services
        user_service = get_user_service()
        auth_service = get_auth_service()
        
        # Authenticate user
        user = await user_service.authenticate_user(login_data.username, login_data.password)
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        # Create access token
        access_token_expires = timedelta(minutes=30)
        access_token = auth_service.create_access_token(user=user, expires_delta=access_token_expires)
        
        # Get user permissions
        permissions = auth_service.get_user_permissions(user.role)
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": 30 * 60,
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role.value,
            "permissions": [p.value for p in permissions]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Login Test Server"}

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting login test server...")
    uvicorn.run(app, host="0.0.0.0", port=8003, log_level="info")