from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
import bcrypt
import jwt

from backend.core.config import settings
from backend.db import repositories as repo

router = APIRouter(prefix="/api/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    user_role: str

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str
    nationality: Optional[str] = "Unknown"

class RegisterResponse(BaseModel):
    message: str
    user_id: int

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt

def get_current_user_id(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return user_id
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest):
    user = repo.get_user_by_email(request.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not bcrypt.checkpw(request.password.encode('utf-8'), user['password'].encode('utf-8')):
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    access_token_expires = timedelta(minutes=60 * 24) # 24 hours
    access_token = create_access_token(
        data={"sub": user["user_id"], "role": user["user_role"]}, expires_delta=access_token_expires
    )
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user["user_id"],
        user_role=user["user_role"]
    )

@router.post("/register", response_model=RegisterResponse)
def register(request: RegisterRequest):
    # Validate role
    role = request.role.lower().strip()
    if role not in ["user", "artist"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'user' or 'artist'")
        
    # Check if email already exists
    existing_user = repo.get_user_by_email(request.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    # Hash password using bcrypt
    hashed_password = bcrypt.hashpw(request.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    # Create user in db
    result = repo.create_user(
        name=request.name.strip(),
        email=request.email.strip(),
        password_hash=hashed_password,
        role=role,
        nationality=request.nationality.strip() if request.nationality else "Unknown"
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to create user"))
        
    return RegisterResponse(
        message="User registered successfully",
        user_id=result["user_id"]
    )
