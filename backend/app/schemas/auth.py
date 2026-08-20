from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthStatusResponse(BaseModel):
    status: str
