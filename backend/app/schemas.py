from pydantic import BaseModel, ConfigDict


class ClubOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    logo_url: str
    primary_color: str
    accent_color: str


class AdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str


class Me(BaseModel):
    admin: AdminOut
    club: ClubOut
