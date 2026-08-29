import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import JWT_SECRET, JWT_ALGORITHM, JWT_EXP_MINUTES, SANDBOX_ORG

pwd_ctx = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)

def hash_password(pw: str) -> str:
    return pwd_ctx.hash(pw)

def verify_password(pw: str, h: str) -> bool:
    return pwd_ctx.verify(pw, h)

def create_token(user: dict) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXP_MINUTES)
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "org": user["org"],
        "role": user["role"],
        "is_sandbox": user.get("is_sandbox", False),
        "exp": exp,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        raise HTTPException(401, f"Invalid token: {e}")

def get_current_user(request: Request, creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)):
    # Allow sandbox org without token: X-Org: TEST_CLUB header
    sandbox_org = request.headers.get("X-Org") or request.headers.get("x-org")
    if sandbox_org and sandbox_org.strip().lower() == SANDBOX_ORG.lower():
        # Return synthetic sandbox user (no DB) — still check if also has valid token for admin
        return {"id":"sandbox","email":"sandbox@test","org":SANDBOX_ORG,"role":"club","is_sandbox":True}
    # Also allow query param ?sandbox=1 for dev
    if request.query_params.get("sandbox") == "1":
        return {"id":"sandbox","email":"sandbox@test","org":SANDBOX_ORG,"role":"club","is_sandbox":True}
    # Try Bearer first, fallback to cookie on failure
    token = None
    if creds and creds.credentials:
        token = creds.credentials
        try:
            payload = decode_token(token)
            # success
            from .state import get_user_by_id as _g
            user = _g(payload["sub"]) if payload.get("sub") != "sandbox" else None
            if user or payload.get("sub") == "sandbox":
                return user or payload
        except:
            # Bearer failed — fallback to cookie
            token = None
    if not token:
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(401, "Not authenticated")
        payload = decode_token(token)
    # Fetch fresh user to ensure not deleted
    from .state import get_user_by_id
    user = get_user_by_id(payload["sub"]) if payload.get("sub") != "sandbox" else None
    if not user and payload.get("sub") != "sandbox":
        raise HTTPException(401, "User not found")
    return user or payload  # sandbox payload itself

def require_role(role: str):
    def checker(user=Depends(get_current_user)):
        if user["role"] != role:
            raise HTTPException(403, f"Requires {role} role")
        return user
    return checker

def require_org_match(org: str, user: dict):
    if user.get("is_sandbox") and user["org"].lower() == SANDBOX_ORG.lower():
        return True
    if user["role"] == "admin":
        return True
    if user["org"].strip().lower() != org.strip().lower():
        raise HTTPException(403, "Org mismatch")
    return True
