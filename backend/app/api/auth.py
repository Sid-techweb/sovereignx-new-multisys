import jwt
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Security, Response, Request
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models.users import SQLUser
from app.schemas.auth import UserSignupRequest, UserLoginRequest, UserResponse, TokenResponse

logger = logging.getLogger("sovereignx")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter()

SECRET_KEY = settings.API_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except Exception as e:
        logger.debug(f"Token decode error: {e}")
        return None

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    """
    Legacy API Key verification dependency for backwards compatibility.
    """
    if not api_key or api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key"
        )
    return api_key

async def get_current_user_or_api_key(
    request: Request,
    api_key: str = Security(api_key_header),
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    db: Session = Depends(get_db)
):
    """
    Dual Authentication Dependency:
    Authorizes request if EITHER:
    1. Valid X-API-Key header is present (system/tool access)
    2. Valid JWT token is in Authorization Bearer header or sovereignx_session cookie (user login)
    """
    # 1. Check X-API-Key
    if api_key and api_key == settings.API_KEY:
        return {"auth_type": "api_key", "username": "system"}

    # 2. Check Authorization Bearer header or Session Cookie
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif "sovereignx_session" in request.cookies:
        token = request.cookies.get("sovereignx_session")

    if token:
        payload = decode_token(token)
        if payload and "sub" in payload:
            user = db.query(SQLUser).filter(SQLUser.username == payload["sub"]).first()
            if user:
                return {"auth_type": "jwt", "user": user, "username": user.username}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Provide a valid session or X-API-Key."
    )

@router.post("/auth/signup", response_model=TokenResponse)
async def signup(req: UserSignupRequest, response: Response, db: Session = Depends(get_db)):
    """
    Self-serve user registration endpoint:
    - Validates minimum password length (>=8 chars).
    - Rejects duplicate usernames cleanly with HTTP 400.
    - Hashes password with bcrypt.
    - Auto-logins user on success, issuing JWT token and setting HttpOnly cookie.
    """
    if len(req.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long."
        )

    existing_user = db.query(SQLUser).filter(SQLUser.username == req.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered."
        )

    hashed = hash_password(req.password)
    user = SQLUser(
        username=req.username,
        email=req.email,
        password_hash=hashed
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.username, "id": user.id})
    response.set_cookie(
        key="sovereignx_session",
        value=token,
        httponly=True,
        max_age=86400,
        samesite="lax"
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )

@router.post("/auth/login", response_model=TokenResponse)
async def login(req: UserLoginRequest, response: Response, db: Session = Depends(get_db)):
    """
    User login endpoint:
    - Validates credentials against bcrypt password hash.
    - Returns 401 Unauthorized if invalid.
    - Issues JWT token and sets HttpOnly cookie.
    """
    user = db.query(SQLUser).filter(SQLUser.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )

    token = create_access_token({"sub": user.username, "id": user.id})
    response.set_cookie(
        key="sovereignx_session",
        value=token,
        httponly=True,
        max_age=86400,
        samesite="lax"
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.from_orm(user)
    )

@router.post("/auth/logout")
async def logout(response: Response):
    """
    User logout endpoint: clears session cookie.
    """
    response.delete_cookie(key="sovereignx_session")
    return {"message": "Logged out successfully"}

@router.get("/auth/me")
async def get_current_user_profile(auth_info: dict = Depends(get_current_user_or_api_key)):
    """
    Returns authenticated profile info.
    """
    if auth_info.get("auth_type") == "jwt":
        user = auth_info["user"]
        return {
            "authenticated": True,
            "username": user.username,
            "email": user.email,
            "auth_type": "user_session"
        }
    return {
        "authenticated": True,
        "username": "system_api_key",
        "auth_type": "api_key"
    }
