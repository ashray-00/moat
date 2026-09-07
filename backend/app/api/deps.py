from fastapi import Header, HTTPException
import jwt   # PyJWT
from app.config import settings

async def current_user(authorization: str = Header(...)) -> str:
    try:
        token = authorization.removeprefix("Bearer ").strip()
        payload = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"],
                             audience="authenticated")
        return payload["sub"]           # the user_id
    except Exception:
        raise HTTPException(401, "invalid token")