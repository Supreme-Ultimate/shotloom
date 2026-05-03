"""
微信网页授权登录（扫码/公众号网页）
流程：前端 → /api/auth/wechat/login → 微信授权页 → 扫码 → 回调 /api/auth/wechat/callback → 签发 JWT → 重定向到前端
"""
import secrets
import urllib.parse
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from database import get_db, User, Credits, CreditTransaction
from auth import create_access_token, set_auth_cookie
from config import WECHAT_APP_ID, WECHAT_APP_SECRET, WECHAT_CALLBACK_URL, FRONTEND_URL, INITIAL_CREDITS

router = APIRouter(prefix="/api/auth/wechat", tags=["wechat"])

WECHAT_AUTHORIZE_URL = "https://open.weixin.qq.com/connect/qrconnect"
WECHAT_TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"
_oauth_states: set[str] = set()
_login_codes: dict[str, str] = {}


@router.get("/login")
def wechat_login():
    """重定向到微信 OAuth2 授权页（网站应用扫码登录）"""
    if not WECHAT_APP_ID:
        raise HTTPException(501, "微信登录未配置，请设置 WECHAT_APP_ID 和 WECHAT_APP_SECRET")

    state = secrets.token_urlsafe(24)
    _oauth_states.add(state)
    params = {
        "appid": WECHAT_APP_ID,
        "redirect_uri": WECHAT_CALLBACK_URL,
        "response_type": "code",
        "scope": "snsapi_login",
        "state": state,
    }
    url = WECHAT_AUTHORIZE_URL + "?" + urllib.parse.urlencode(params) + "#wechat_redirect"
    return RedirectResponse(url)


@router.get("/callback")
async def wechat_callback(code: str, state: str = "", db: Session = Depends(get_db)):
    """微信回调：用 code 换取 openid，创建/查找用户，签发 JWT"""
    import httpx

    if not WECHAT_APP_ID or not WECHAT_APP_SECRET:
        raise HTTPException(501, "微信登录未配置")
    if not state or state not in _oauth_states:
        raise HTTPException(400, "微信授权状态无效或已过期")
    _oauth_states.discard(state)

    # 1. 用 code 换 access_token + openid
    async with httpx.AsyncClient() as client:
        resp = await client.get(WECHAT_TOKEN_URL, params={
            "appid": WECHAT_APP_ID,
            "secret": WECHAT_APP_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        })
    data = resp.json()

    if "errcode" in data:
        raise HTTPException(400, f"微信授权失败: {data.get('errmsg', data['errcode'])}")

    openid = data["openid"]
    nickname = data.get("nickname", "微信用户")

    # 2. 查找或创建用户
    user = db.query(User).filter(User.wechat_openid == openid).first()
    if not user:
        # 用 unionid 或 openid 生成唯一邮箱占位（不用于登录，仅作唯一键）
        fake_email = f"wx_{openid}@wechat.placeholder"
        user = User(
            email=fake_email,
            hashed_password=None,
            display_name=nickname,
            wechat_openid=openid,
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
        db.add(user)
        db.flush()
        # 初始化积分
        db.add(Credits(user_id=user.id, balance=INITIAL_CREDITS))
        db.add(CreditTransaction(
            user_id=user.id,
            delta=INITIAL_CREDITS,
            reason="initial_grant",
        ))
        db.commit()
        db.refresh(user)

    # 3. 签发 JWT，并用一次性 code 带回前端，避免 token 进入 URL 历史
    token = create_access_token(user.id)
    login_code = secrets.token_urlsafe(32)
    _login_codes[login_code] = token
    redirect_url = f"{FRONTEND_URL}/login?wechat_code={login_code}"
    return RedirectResponse(redirect_url)


@router.post("/exchange")
def exchange_wechat_login_code(code: str, response: Response):
    token = _login_codes.pop(code, None)
    if not token:
        raise HTTPException(400, "微信登录凭证无效或已过期")
    set_auth_cookie(response, token)
    return {"access_token": token, "token_type": "bearer"}
