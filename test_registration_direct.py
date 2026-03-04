#!/usr/bin/env python3
"""
Direct test of registration functionality.
"""

import sys
import traceback
sys.path.insert(0, '.')

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from src.multimodal_librarian.services.user_service import get_user_service, UserRegistrationRequest
from src.multimodal_librarian.security.auth import UserRole, AuthenticationError
from src.multimodal_librarian.logging_config import configure_logging, get_logger

# Configure logging
configure_logging()
logger = get_logger(__name__)

app = FastAPI(title="Registration Test")

class UserRegistrationRequestAPI(BaseModel):
    username: str
    email: str
    password: str
    role: str = "user"

@app.post("/register")
async def register_user(registration_data: UserRegistrationRequestAPI):
    """Test registration endpoint."""
    try:
        logger.info(f"Registration request: {registration_data.username}")
        
        # Validate role
        try:
            role = UserRole(registration_data.role)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid role: {registration_data.role}")
        
        # Get user service
        user_service = get_user_service()
        
        # Create registration request
        registration = UserRegistrationRequest(
            username=registration_data.username,
            email=registration_data.email,
            password=registration_data.password,
            role=role
        )
        
        # Register user
        user = await user_service.register_user(registration)
        
        return {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
            "message": "User registered successfully"
        }
        
    except AuthenticationError as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Registration error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Registration Test Server"}

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting registration test server...")
    uvicorn.run(app, host="0.0.0.0", port=8002, log_level="info")