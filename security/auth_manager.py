from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import bcrypt

from security.access_control import AccessController
from security.pin_manager import set_pin
from security.security_config import AUTH_COOKIE_MAX_AGE_SECONDS, AUTH_COOKIE_NAME, AUTH_COOKIE_SAMESITE, USERS_FILE
from security.session_manager import create_login_session, get_login_session, invalidate_login_session


def _now_string() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")


def load_users() -> Dict[str, Dict[str, Any]]:
    if not USERS_FILE.exists():
        return {}
    try:
        payload = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def save_users(users: Dict[str, Dict[str, Any]]) -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, indent=2, ensure_ascii=False), encoding="utf-8")


def sanitize_user(user: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not user:
        return None
    return {
        "id": user.get("id", ""),
        "username": user.get("username", ""),
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "created": user.get("created", ""),
        "last_login": user.get("last_login", ""),
        "admin": bool(user.get("admin", False)),
        "owner": bool(user.get("owner", False)),
        "title": user.get("title", "sir"),
        "preferred_name": user.get("preferred_name", ""),
        "plan": user.get("plan", "private"),
    }


def users_exist() -> bool:
    return bool(load_users())


def get_user(username: str | None) -> Optional[Dict[str, Any]]:
    normalized = str(username or "").strip().lower()
    if not normalized:
        return None
    return sanitize_user(load_users().get(normalized))


def get_user_record(username: str | None) -> Optional[Dict[str, Any]]:
    normalized = str(username or "").strip().lower()
    if not normalized:
        return None
    return load_users().get(normalized)


def get_user_by_id(user_id: str | None) -> Optional[Dict[str, Any]]:
    normalized = str(user_id or "").strip()
    if not normalized:
        return None
    for user in load_users().values():
        if user.get("id") == normalized:
            return sanitize_user(user)
    return None


def requires_first_run_setup() -> bool:
    users = load_users()
    return not any(bool(user.get("owner")) for user in users.values())


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _build_user_record(*, username: str, password: str, name: str, email: str, admin: bool, owner: bool, title: str = "sir", preferred_name: str = "") -> Dict[str, Any]:
    return {
        "id": secrets.token_hex(12),
        "username": username,
        "password": _hash_password(password),
        "name": name,
        "email": email,
        "created": _now_string(),
        "last_login": "",
        "plan": "private",
        "admin": bool(admin),
        "owner": bool(owner),
        "title": title or "sir",
        "preferred_name": preferred_name or "",
    }


def create_owner_account(*, username: str, password: str, name: str, email: str, master_pin: str, title: str = "sir", preferred_name: str = "") -> Tuple[bool, Dict[str, Any] | str]:
    username = str(username or "").strip().lower()
    password = str(password or "").strip()
    name = str(name or "").strip()
    email = str(email or "").strip().lower()
    master_pin = str(master_pin or "").strip()

    if not requires_first_run_setup():
        return False, "Owner account already exists."
    if not username or len(username) < 3:
        return False, "Username must be at least 3 characters."
    if not name:
        return False, "Name is required."
    if "@" not in email:
        return False, "A valid email is required."
    if len(password) < 8:
        return False, "Password must be at least 8 characters."

    pin_result = set_pin(master_pin)
    if not pin_result.get("success"):
        return False, str(pin_result.get("reason") or "Master PIN could not be saved.")

    access_controller = AccessController()
    access_controller.invite_user(email, invited_by_admin="owner_setup", admin=True)

    users = load_users()
    if username in users:
        return False, "Username already exists."
    users[username] = _build_user_record(
        username=username,
        password=password,
        name=name,
        email=email,
        admin=True,
        owner=True,
        title=title,
        preferred_name=preferred_name,
    )
    save_users(users)
    access_controller.mark_registered(email, username=username, admin=True)
    return True, sanitize_user(users[username])


def register_user(username: str, password: str, name: str, email: str | None = None, *, title: str = "sir", preferred_name: str = "") -> Tuple[bool, Dict[str, Any] | str]:
    username = str(username or "").strip().lower()
    password = str(password or "").strip()
    name = str(name or "").strip()
    email = str(email or "").strip().lower()

    if not username or len(username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password) < 8:
        return False, "Password must be at least 8 characters."
    if not name:
        return False, "Name is required."
    if "@" not in email:
        return False, "A valid email is required."

    access_controller = AccessController()
    if not access_controller.is_whitelisted(email):
        access_controller.invite_user(email, invited_by_admin="open_registration")

    users = load_users()
    if username in users:
        return False, "Username already exists."
    if any(str(user.get("email", "")).strip().lower() == email for user in users.values()):
        return False, "That email is already registered."

    users[username] = _build_user_record(
        username=username,
        password=password,
        name=name,
        email=email,
        admin=False,
        owner=False,
        title=title,
        preferred_name=preferred_name,
    )
    save_users(users)
    access_controller.mark_registered(email, username=username, admin=False)
    return True, sanitize_user(users[username])


def authenticate_user(username: str, password: str, *, ip_address: str, user_agent: str) -> Tuple[bool, Dict[str, Any] | str, str | None]:
    username = str(username or "").strip().lower()
    password = str(password or "").strip()
    access_controller = AccessController()

    if access_controller.is_ip_blocked(ip_address):
        return False, "Too many failed login attempts. This IP is temporarily blocked.", None

    users = load_users()
    user = users.get(username)
    if not user:
        access_controller.record_login_attempt(ip_address, success=False)
        return False, "Username not found.", None

    if not _verify_password(password, str(user.get("password", ""))):
        access_controller.record_login_attempt(ip_address, success=False)
        return False, "Wrong password.", None

    access_controller.record_login_attempt(ip_address, success=True)
    user["last_login"] = _now_string()
    users[username] = user
    save_users(users)
    access_controller.mark_last_login(str(user.get("email", "")))
    session_token = create_login_session(
        user_id=str(user.get("id")),
        username=username,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return True, sanitize_user(user), session_token


def get_auth_state(username: str | None) -> Dict[str, object]:
    user = get_user(username)
    return {"authenticated": bool(user), "user": user}


def get_request_user(request) -> Optional[Dict[str, Any]]:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return None
    session = get_login_session(token)
    if not session:
        return None
    user = get_user(session.get("username"))
    if not user:
        invalidate_login_session(token)
        return None
    return user


def set_session_cookie(response, session_token: str, *, secure: bool) -> None:
    response.set_cookie(
        AUTH_COOKIE_NAME,
        session_token,
        max_age=AUTH_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=secure,
        samesite=AUTH_COOKIE_SAMESITE,
        path="/",
    )


def clear_session_cookie(response, *, secure: bool) -> None:
    response.delete_cookie(
        AUTH_COOKIE_NAME,
        httponly=True,
        secure=secure,
        samesite=AUTH_COOKIE_SAMESITE,
        path="/",
    )


def logout_request(request) -> None:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token:
        invalidate_login_session(token)


def validate_login(username: str, password: str) -> Dict[str, object]:
    success, result, _token = authenticate_user(username, password, ip_address="local", user_agent="internal")
    return {"success": success, "user": result if success else None, "reason": None if success else result}


def is_admin_user(user: Optional[Dict[str, Any]]) -> bool:
    return bool(user and user.get("admin"))
