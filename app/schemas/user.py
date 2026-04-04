from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.user import UserPlan


class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    email: str
    username: str
    plan: UserPlan
    credits: int
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
