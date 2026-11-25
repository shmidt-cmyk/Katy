from __future__ import annotations

from sqlalchemy import select

from .db import SessionLocal
from .hh_api import fetch_public_vacancies
from .models import Vacancy
from .workflow import record_status


def fetch_and_store_public_vacancies() -> tuple[int, int]:
    session = SessionLocal()
    inserted = 0
    already_saved = 0
    try:
        for item in fetch_public_vacancies():
            exists = session.execute(
                select(Vacancy.id).where(Vacancy.url == item.url)
            ).scalar_one_or_none()
            if exists is not None:
                already_saved += 1
                continue
            session.add(
                Vacancy(
                    title=item.title,
                    employer_name=item.employer_name,
                    city=item.city,
                    url=item.url,
                    description=item.description,
                    salary=item.salary,
                    source="hh_api",
                    status="new",
                )
            )
            inserted += 1
        session.commit()
        return inserted, already_saved
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_vacancies_to_review() -> list[Vacancy]:
    session = SessionLocal()
    try:
        vacancies = session.execute(
            select(Vacancy)
            .where(Vacancy.status == "new")
            .order_by(Vacancy.created_at, Vacancy.id)
        ).scalars().all()
        session.expunge_all()
        return vacancies
    finally:
        session.close()


def mark_vacancy_sent_for_review(vacancy_id: int, message_id: int) -> None:
    session = SessionLocal()
    try:
        record_status(
            session,
            vacancy_id,
            "review_pending",
            f"Карточка отправлена в Telegram (message_id={message_id}) для оценки.",
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
