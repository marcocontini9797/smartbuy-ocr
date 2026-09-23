"""
SmartBuy Authentication Models v1
"""

from __future__ import annotations


from pydantic import BaseModel, Field


from uuid import uuid4


from datetime import datetime, timezone





def utcnow():

    return datetime.now(
        timezone.utc
    ).isoformat()





class User(BaseModel):

    id: str = Field(

        default_factory=lambda:

        str(uuid4())

    )


    email: str


    password_hash: str


    is_active: bool = True


    created_at: str = Field(

        default_factory=utcnow

    )





class LoginRequest(BaseModel):

    email: str

    password: str





class TokenResponse(BaseModel):

    access_token: str

    token_type: str = "bearer"