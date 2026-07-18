from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
import os
import requests
import secrets

from exporter.db import store

router = APIRouter()

class UserCreate(BaseModel):
    email: str
    password: str

class GoogleAuth(BaseModel):
    credential: str

class Token(BaseModel):
    access_token: str
    token_type: str

SECRET_KEY = os.environ.get("JWT_SECRET", "super-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 1 week

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

from fastapi import APIRouter, Depends, HTTPException, status, Request

def get_current_user_id(request: Request, token: str = Depends(oauth2_scheme)) -> int:
    # Also allow token as query param for browser-opened links (e.g. invoices)
    query_token = request.query_params.get("token")
    if query_token:
        token = query_token
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        return int(user_id)
    except JWTError:
        raise credentials_exception

@router.post("/register", response_model=Token)
def register(user: UserCreate):
    existing = store.get_user_by_email(user.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    hashed = get_password_hash(user.password)
    user_id = store.create_user(user.email, hashed)
    
    # Read free credits from settings
    free_credits = int(store.get_setting("free_credits", "10"))
    if free_credits > 0:
        store.add_credits(user_id, free_credits)
        
    token = create_access_token(data={"sub": str(user_id)})
    return {"access_token": token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = store.get_user_by_email(form_data.username) # OAuth2 uses 'username' for email
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = create_access_token(data={"sub": str(user["id"])})
    return {"access_token": token, "token_type": "bearer"}

@router.get("/me")
def read_users_me(user_id: int = Depends(get_current_user_id)):
    user = store.get_user_by_id(user_id)
    return {"email": user["email"], "credits": user["credits"], "is_admin": user["is_admin"]}

@router.post("/google", response_model=Token)
def login_google(auth: GoogleAuth):
    # Verify the token using Google's tokeninfo endpoint
    try:
        resp = requests.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={auth.credential}", timeout=10)
        resp.raise_for_status()
        info = resp.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid Google token")

    email = info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Google token did not contain an email")

    user = store.get_user_by_email(email)
    if not user:
        # Register new user with a random unguessable password
        hashed = get_password_hash(secrets.token_urlsafe(32))
        user_id = store.create_user(email, hashed)
        
        # Read free credits from settings
        free_credits = int(store.get_setting("free_credits", "10"))
        if free_credits > 0:
            store.add_credits(user_id, free_credits)
    else:
        user_id = user["id"]

    token = create_access_token(data={"sub": str(user_id)})
    return {"access_token": token, "token_type": "bearer"}
