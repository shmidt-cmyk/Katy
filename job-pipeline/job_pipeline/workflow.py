from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ApplicationEvent, GeneratedLetter, Vacancy

ALLOWED_STATUSES = {
    "new",
    "review_pending",
    "liked",
    "disliked",
    "generating",
    "letter_ready",
}


def record_status(
    session: Session,
    vacancy_id: int,
    status: str,
    note: str | None = None,
) -> Vacancy:
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"Unsupported status: {status}")
    vacancy = session.get(Vacancy, vacancy_id)
    if vacancy is None:
        raise ValueError(f"Vacancy {vacancy_id} was not found")
    vacancy.status = status
    session.add(ApplicationEvent(vacancy_id=vacancy_id, status=status, note=note))
    return vacancy


def get_latest_letter(session: Session, vacancy_id: int) -> GeneratedLetter:
    letter = session.execute(
        select(GeneratedLetter)
        .where(GeneratedLetter.vacancy_id == vacancy_id)
        .order_by(GeneratedLetter.created_at.desc(), GeneratedLetter.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if letter is None:
        raise ValueError(f"No generated cover letter exists for vacancy {vacancy_id}")
    return letter


def require_positive_rating(vacancy: Vacancy) -> None:
    if vacancy.status not in {"liked", "generating"}:
        raise ValueError("A cover letter can only be generated after the vacancy is liked")
