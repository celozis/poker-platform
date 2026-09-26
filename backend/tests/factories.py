from app.db import SessionLocal
from app.models import Admin, Club


def create_club(
    name: str = "Тестовый клуб",
    primary_color: str = "#111111",
    accent_color: str = "#EEEEEE",
) -> Club:
    with SessionLocal(expire_on_commit=False) as session:
        club = Club(
            name=name,
            logo_url="/logos/test.svg",
            primary_color=primary_color,
            accent_color=accent_color,
        )
        session.add(club)
        session.commit()
        return club


def create_admin(club: Club, phone: str, name: str = "Администратор") -> Admin:
    with SessionLocal(expire_on_commit=False) as session:
        admin = Admin(club_id=club.id, phone=phone, name=name)
        session.add(admin)
        session.commit()
        return admin
