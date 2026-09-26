"""Creates the two test clubs with one admin each. Safe to run again: it updates in place.

    python -m app.seed
"""

from dataclasses import dataclass

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Admin, Club


@dataclass(frozen=True)
class SeedClub:
    name: str
    logo_url: str
    primary_color: str
    accent_color: str
    admin_name: str
    admin_phone: str


SEED_CLUBS = [
    SeedClub(
        name="Покер-клуб «Обь»",
        logo_url="/logos/ob.svg",
        primary_color="#0B3D91",
        accent_color="#F2A900",
        admin_name="Анна Соколова",
        admin_phone="+79990000001",
    ),
    SeedClub(
        name="Покер-клуб «Енисей»",
        logo_url="/logos/enisey.svg",
        primary_color="#7A1F2B",
        accent_color="#E8C07D",
        admin_name="Дмитрий Орлов",
        admin_phone="+79990000002",
    ),
]


def seed() -> None:
    with SessionLocal() as session:
        for data in SEED_CLUBS:
            club = session.scalar(select(Club).where(Club.name == data.name)) or Club(name=data.name)
            club.logo_url = data.logo_url
            club.primary_color = data.primary_color
            club.accent_color = data.accent_color
            session.add(club)
            session.flush()

            admin = session.scalar(select(Admin).where(Admin.phone == data.admin_phone))
            admin = admin or Admin(phone=data.admin_phone)
            admin.name = data.admin_name
            admin.club_id = club.id
            session.add(admin)
        session.commit()


if __name__ == "__main__":
    seed()
    for data in SEED_CLUBS:
        print(f"{data.name}: администратор {data.admin_name}, телефон {data.admin_phone}")
