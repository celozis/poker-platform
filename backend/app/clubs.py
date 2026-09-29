"""Club-scoped API: every route lives under /api/clubs/{club_id} and depends on AdminClub.

See docs/adr/ADR-0003-multi-tenancy.md for why access is enforced here.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import CurrentAdmin
from app.models import Club
from app.schemas import ClubOut

router = APIRouter(prefix="/api/clubs/{club_id}")


def admin_club(club_id: int, admin: CurrentAdmin) -> Club:
    """The club from the URL, but only if it is the logged-in admin's own club."""
    if admin.club_id != club_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к этому клубу")
    return admin.club


AdminClub = Annotated[Club, Depends(admin_club)]


@router.get("")
def get_club(club: AdminClub) -> ClubOut:
    return ClubOut.model_validate(club)


def owner_club(club: AdminClub, admin: CurrentAdmin) -> Club:
    """The admin's own club, but only for its owner: the club's reports are the owner's alone."""
    if admin.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Отчёты клуба видит только владелец")
    return club


OwnerClub = Annotated[Club, Depends(owner_club)]
