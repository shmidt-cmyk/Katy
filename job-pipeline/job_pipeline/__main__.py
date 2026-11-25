from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .db import SessionLocal, init_db
from .gemini_client import generate_cover_letter
from .models import Vacancy
from .telegram_bot import run_bot, send_vacancy_for_review
from .vacancy_service import (
    fetch_and_store_public_vacancies,
    get_vacancies_to_review,
    mark_vacancy_sent_for_review,
)
from .workflow import ALLOWED_STATUSES, record_status


def _add_vacancy(args: argparse.Namespace) -> None:
    description = (
        Path(args.description_file).read_text(encoding="utf-8")
        if args.description_file
        else args.description
    )
    session = SessionLocal()
    try:
        vacancy = Vacancy(
            title=args.title,
            employer_name=args.company,
            city=args.city,
            url=args.url,
            description=description,
            salary=args.salary,
            source="manual",
            status="new",
        )
        session.add(vacancy)
        session.commit()
        print(json.dumps({"id": vacancy.id, "status": vacancy.status}, ensure_ascii=False))
    except IntegrityError as exc:
        session.rollback()
        raise ValueError("This vacancy URL has already been added") from exc
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _generate(vacancy_id: int) -> None:
    letter = generate_cover_letter(vacancy_id)
    print(json.dumps({"letter_id": letter.id, "vacancy_id": vacancy_id}, ensure_ascii=False))


def _fetch() -> None:
    inserted, already_saved = fetch_and_store_public_vacancies()
    print(json.dumps({"added": inserted, "already_saved": already_saved}, ensure_ascii=False))


def _review_new_vacancies() -> None:
    sent = 0
    for vacancy in get_vacancies_to_review():
        message_id = asyncio.run(send_vacancy_for_review(vacancy))
        mark_vacancy_sent_for_review(vacancy.id, message_id)
        sent += 1
    print(json.dumps({"sent_for_review": sent}, ensure_ascii=False))


def _list_vacancies() -> None:
    session = SessionLocal()
    try:
        records = session.execute(
            select(Vacancy).order_by(Vacancy.created_at.desc(), Vacancy.id.desc())
        ).scalars()
        for vacancy in records:
            print(
                json.dumps(
                    {
                        "id": vacancy.id,
                        "title": vacancy.title,
                        "company": vacancy.employer_name,
                        "url": vacancy.url,
                        "status": vacancy.status,
                        "source": vacancy.source,
                    },
                    ensure_ascii=False,
                )
            )
    finally:
        session.close()


def _set_status(vacancy_id: int, status: str, note: str | None) -> None:
    session = SessionLocal()
    try:
        vacancy = record_status(session, vacancy_id, status, note)
        session.commit()
        print(json.dumps({"id": vacancy.id, "status": vacancy.status}, ensure_ascii=False))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Public vacancy collection and manual ratings (no login or automatic applications)"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="Create only the jobpipe_* tables in the configured database")

    add = commands.add_parser("add", help="Manually import a vacancy")
    add.add_argument("--title", required=True)
    add.add_argument("--company", default="")
    add.add_argument("--city", default="")
    add.add_argument("--url", required=True)
    add.add_argument("--salary", default="")
    description_group = add.add_mutually_exclusive_group(required=True)
    description_group.add_argument("--description")
    description_group.add_argument("--description-file")

    generate = commands.add_parser("generate", help="Generate a cover letter for a vacancy")
    generate.add_argument("--id", type=int, required=True)

    commands.add_parser("fetch", help="Collect public vacancy search results from the HH API")
    commands.add_parser("review", help="Send new vacancies to Telegram for like/dislike")
    commands.add_parser("bot", help="Run the Telegram approval/status bot")
    commands.add_parser("list", help="List collected and manually imported vacancies")

    set_status = commands.add_parser("set-status", help="Record a manually observed application status")
    set_status.add_argument("--id", type=int, required=True)
    set_status.add_argument("--status", choices=sorted(ALLOWED_STATUSES), required=True)
    set_status.add_argument("--note")

    args = parser.parse_args()
    if args.command == "init-db":
        init_db()
    elif args.command == "add":
        _add_vacancy(args)
    elif args.command == "fetch":
        _fetch()
    elif args.command == "review":
        _review_new_vacancies()
    elif args.command == "generate":
        _generate(args.id)
    elif args.command == "bot":
        run_bot()
    elif args.command == "list":
        _list_vacancies()
    elif args.command == "set-status":
        _set_status(args.id, args.status, args.note)


if __name__ == "__main__":
    main()
