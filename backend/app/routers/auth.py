from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.services import user_service

router = APIRouter()


class RegisterRequest(BaseModel):
    phone: str
    nickname: Optional[str] = None
    invite_token: str


class LoginRequest(BaseModel):
    phone: str


class UserOut(BaseModel):
    id: int
    phone: str
    nickname: Optional[str]
    user_id: str   # external id used as user_id everywhere downstream
    auth_token: str


def _to_out(user: dict) -> UserOut:
    return UserOut(
        id=user["id"],
        phone=user["phone"],
        nickname=user["nickname"],
        user_id=user_service.user_to_external_id(user),
        auth_token=user["auth_token"],
    )


@router.post("/auth/register", response_model=UserOut)
async def register(req: RegisterRequest):
    if settings.REGISTER_TOKEN and req.invite_token != settings.REGISTER_TOKEN:
        raise HTTPException(status_code=403, detail="邀请码错误")
    if not user_service.is_valid_phone(req.phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确")
    if await user_service.get_user_by_phone(req.phone):
        raise HTTPException(status_code=409, detail="该手机号已注册，请直接登录")
    user = await user_service.register_user(req.phone, req.nickname)
    return _to_out(user)


@router.post("/auth/login", response_model=UserOut)
async def login(req: LoginRequest):
    if not user_service.is_valid_phone(req.phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确")
    user = await user_service.login_user(req.phone)
    if not user:
        raise HTTPException(status_code=404, detail="该手机号未注册")
    return _to_out(user)


@router.get("/auth/me", response_model=UserOut)
async def me(authorization: Optional[str] = Header(None)):
    token = _parse_bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    user = await user_service.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return _to_out(user)


def _parse_bearer(auth_header: Optional[str]) -> Optional[str]:
    if not auth_header:
        return None
    parts = auth_header.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


# Required-auth dependency: raises 401 if not logged in.
# Anonymous access is no longer supported — all business endpoints must use this.
async def require_user_id(authorization: Optional[str] = Header(None)) -> str:
    token = _parse_bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    user = await user_service.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return user_service.user_to_external_id(user)
