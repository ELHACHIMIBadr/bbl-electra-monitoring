"""
Routes d'authentification - Login, gestion utilisateurs
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.models.models import User, UserRole
from app.auth.auth import (
    verify_password, hash_password, create_token,
    require_auth, require_admin
)

auth_router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: Optional[str] = "engineer"


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    receive_alerts: Optional[bool] = None


@auth_router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

    if not user.is_active:
        raise HTTPException(status_code=401, detail="Compte désactivé")

    token = create_token({"sub": str(user.id), "email": user.email, "role": user.role.value})

    return {
        "token": token,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role.value
        }
    }


@auth_router.get("/me")
def get_me(user: User = Depends(require_auth)):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role.value,
        "receive_alerts": user.receive_alerts
    }


@auth_router.get("/users")
def list_users(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id).all()
    return [
        {
            "id": u.id, "name": u.name, "email": u.email,
            "role": u.role.value, "is_active": u.is_active,
            "receive_alerts": u.receive_alerts,
            "created_at": u.created_at.isoformat() if u.created_at else None
        }
        for u in users
    ]


@auth_router.post("/users")
def create_user(req: UserCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email déjà utilisé")

    role = UserRole.ADMIN if req.role == "admin" else UserRole.ENGINEER if req.role == "engineer" else UserRole.VIEWER

    user = User(
        name=req.name,
        email=req.email,
        password_hash=hash_password(req.password),
        role=role,
        is_active=True,
        receive_alerts=True
    )
    db.add(user)
    db.commit()

    return {"message": f"Utilisateur {req.name} créé", "id": user.id}


@auth_router.put("/users/{user_id}")
def update_user(user_id: int, req: UserUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    if req.name is not None:
        user.name = req.name
    if req.email is not None:
        user.email = req.email
    if req.password is not None:
        user.password_hash = hash_password(req.password)
    if req.role is not None:
        user.role = UserRole.ADMIN if req.role == "admin" else UserRole.ENGINEER if req.role == "engineer" else UserRole.VIEWER
    if req.is_active is not None:
        user.is_active = req.is_active
    if req.receive_alerts is not None:
        user.receive_alerts = req.receive_alerts

    db.commit()
    return {"message": f"Utilisateur {user.name} mis à jour"}


@auth_router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Impossible de supprimer votre propre compte")

    db.delete(user)
    db.commit()
    return {"message": f"Utilisateur {user.name} supprimé"}
