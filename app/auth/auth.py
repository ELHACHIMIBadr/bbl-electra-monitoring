"""
Authentification JWT - Login, tokens, protection des routes
"""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import User, UserRole
import logging

logger = logging.getLogger(__name__)

SECRET_KEY = "bbl-electra-monitoring-secret-key-change-in-production-2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 72

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))


def create_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)) -> Optional[User]:
    if not credentials:
        return None
    payload = decode_token(credentials.credentials)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return db.query(User).filter(User.id == int(user_id)).first()


def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Non authentifié")
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")
    user = db.query(User).filter(User.id == int(payload.get("sub", 0))).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")
    return user


def require_admin(user: User = Depends(require_auth)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return user


def init_default_users(db: Session):
    if db.query(User).count() > 0:
        return

    users = [
        {"name": "Admin 1", "email": "admin1", "password": "admin", "role": UserRole.ADMIN},
        {"name": "Admin 2", "email": "admin2", "password": "admin", "role": UserRole.ADMIN},
        {"name": "Admin 3", "email": "admin3", "password": "admin", "role": UserRole.ADMIN},
    ]

    for u in users:
        user = User(
            name=u["name"], email=u["email"],
            password_hash=hash_password(u["password"]),
            role=u["role"], is_active=True, receive_alerts=True
        )
        db.add(user)
        logger.info(f"   ✅ Utilisateur créé: {u['name']}")

    db.commit()
    logger.info("✅ Utilisateurs par défaut initialisés")
