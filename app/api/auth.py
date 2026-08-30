import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_async_db
from app.models.user import User
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, RefreshRequest
from app.auth.password import hash_password, verify_password
from app.auth.jwt import create_access_token, create_refresh_token, decode_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(User).where(or_(User.email == payload.email, User.username == payload.username)))
    existing = result.scalar_one_or_none()
    if existing:
        if existing.email == payload.email:
            raise HTTPException(status_code=409, detail="Email already registered")
        if existing.username == payload.username:
            raise HTTPException(status_code=409, detail="Username already registered")
        
    user = User(username=payload.username, email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return {"id": str(user.id), "username": user.username, "email": user.email}

@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )

@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest):
    try:
        claims = decode_token(payload.refresh_token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
        
    if claims.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Wrong token type")
        
    return TokenResponse(
        access_token=create_access_token(claims["sub"]),
        refresh_token=create_refresh_token(claims["sub"])
    )
