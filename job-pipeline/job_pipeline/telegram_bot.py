from __future__ import annotations

import asyncio
import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from .config import get_settings
from .db import SessionLocal
from .gemini_client import generate_cover_letter, generate_demo_cover_letter
from .hh_api import HHAPIAccessDeniedError, fetch_public_vacancy_description
from .models import Vacancy
from .vacancy_service import (
    fetch_and_store_public_vacancies,
    get_vacancies_to_review,
    mark_vacancy_sent_for_review,
)
from .workflow import record_status

logger = logging.getLogger(__name__)


def _require_bot_config() -> tuple[str, str]:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not configured")
    if not settings.telegram_chat_id:
        raise ValueError("TELEGRAM_CHAT_ID is not configured")
    return settings.telegram_bot_token, settings.telegram_chat_id


def _review_keyboard(vacancy_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👍 Нравится", callback_data=f"like:{vacancy_id}"),
                InlineKeyboardButton("👎 Не нравится", callback_data=f"dislike:{vacancy_id}"),
            ]
        ]
    )


def build_vacancy_message(vacancy: Vacancy) -> str:
    parts = [
        f"Вакансия: {vacancy.title}",
        f"Компания: {vacancy.employer_name or 'не указана'}",
        f"Город: {vacancy.city or 'не указан'}",
        f"Зарплата: {vacancy.salary or 'не указана'}",
        f"Ссылка: {vacancy.url}",
    ]
    if vacancy.description:
        parts.extend(["", vacancy.description[:1800]])
    parts.extend(["", "Оцени вакансию. Письмо создаётся только после нажатия «Нравится»."])
    return "\n".join(parts)


async def send_vacancy_for_review(vacancy: Vacancy) -> int:
    token, chat_id = _require_bot_config()
    async with Bot(token=token) as bot:
        message = await bot.send_message(
            chat_id=chat_id,
            text=build_vacancy_message(vacancy),
            reply_markup=_review_keyboard(vacancy.id),
            disable_web_page_preview=True,
        )
        return message.message_id


async def _handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.message is None:
        return

    settings = get_settings()
    expected_chat_id = str(settings.telegram_chat_id)
    if (
        str(query.message.chat_id) != expected_chat_id
        or str(query.from_user.id) != expected_chat_id
    ):
        await query.answer("Этот чат не настроен для оценки вакансий.", show_alert=True)
        return

    action, separator, vacancy_id_text = (query.data or "").partition(":")
    if not separator or action not in {"like", "dislike"} or not vacancy_id_text.isdigit():
        await query.answer("Неизвестное действие.", show_alert=True)
        return

    vacancy_id = int(vacancy_id_text)
    session = SessionLocal()
    try:
        vacancy = session.get(Vacancy, vacancy_id)
        if vacancy is None:
            await query.answer("Вакансия не найдена.", show_alert=True)
            return
        if vacancy.status not in {"review_pending", "liked"}:
            await query.answer("Эта вакансия уже оценена.", show_alert=True)
            return

        if action == "dislike":
            if vacancy.status != "review_pending":
                await query.answer("Вакансия уже понравилась и ожидает подготовки письма.", show_alert=True)
                return
            record_status(session, vacancy_id, "disliked", "Пользователь оценил вакансию как неподходящую.")
            session.commit()
            await query.answer("Вакансия отмечена как неподходящая.")
            await query.edit_message_reply_markup(reply_markup=None)
            return

        vacancy_url = vacancy.url
        existing_description = vacancy.description
        vacancy_source = vacancy.source
        if vacancy.status == "review_pending":
            record_status(session, vacancy_id, "liked", "Пользователь хочет рассмотреть вакансию.")
        record_status(session, vacancy_id, "generating", "Получаю описание и готовлю черновик письма.")
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    await query.answer("Понравилась — готовлю черновик письма.")
    try:
        if vacancy_source != "manual" or not existing_description:
            description = await asyncio.to_thread(fetch_public_vacancy_description, vacancy_url)
            session = SessionLocal()
            try:
                vacancy = session.get(Vacancy, vacancy_id)
                if vacancy is None:
                    raise ValueError(f"Vacancy {vacancy_id} was not found")
                vacancy.description = description
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        letter_generator = (
            generate_demo_cover_letter if settings.bot_demo_mode else generate_cover_letter
        )
        letter = await asyncio.to_thread(letter_generator, vacancy_id)
    except Exception as exc:
        logger.exception("Could not prepare cover letter for vacancy %s", vacancy_id)
        session = SessionLocal()
        try:
            record_status(
                session,
                vacancy_id,
                "liked",
                f"Не удалось получить описание или сгенерировать письмо ({type(exc).__name__}); можно повторить.",
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        await query.message.reply_text(
            f"Вакансия сохранена как понравившаяся, но подготовить письмо не удалось "
            f"({type(exc).__name__}). Проверь доступность HH API и Gemini; "
            "можно повторить нажатием «Нравится»."
        )
        return

    await query.edit_message_reply_markup(reply_markup=None)
    try:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"Черновик для вакансии #{vacancy_id}:\n\n{letter.letter_text}",
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("Could not deliver generated cover letter for vacancy %s", vacancy_id)
        raise


def run_bot() -> None:
    token, _ = _require_bot_config()
    settings = get_settings()
    if settings.hh_scan_interval_minutes < 60:
        raise ValueError("HH_SCAN_INTERVAL_MINUTES must be at least 60")
    application = (
        Application.builder()
        .token(token)
        .post_init(_start_periodic_scan)
        .post_shutdown(_stop_periodic_scan)
        .build()
    )
    application.add_handler(CallbackQueryHandler(_handle_callback))
    application.run_polling(allowed_updates=Update.ALL_TYPES)


async def _periodic_scan(application: Application) -> None:
    settings = get_settings()
    if settings.bot_demo_mode:
        vacancies = await asyncio.to_thread(get_vacancies_to_review)
        for vacancy in vacancies:
            message = await application.bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=build_vacancy_message(vacancy),
                reply_markup=_review_keyboard(vacancy.id),
                disable_web_page_preview=True,
            )
            await asyncio.to_thread(
                mark_vacancy_sent_for_review,
                vacancy.id,
                message.message_id,
            )
        logger.info("Demo mode: sent %s test vacancies; public scanning is disabled", len(vacancies))
        return

    while True:
        try:
            added, already_saved = await asyncio.to_thread(fetch_and_store_public_vacancies)
            logger.info("HH scan completed: added=%s already_saved=%s", added, already_saved)
            vacancies = await asyncio.to_thread(get_vacancies_to_review)
            for vacancy in vacancies:
                message = await application.bot.send_message(
                    chat_id=settings.telegram_chat_id,
                    text=build_vacancy_message(vacancy),
                    reply_markup=_review_keyboard(vacancy.id),
                    disable_web_page_preview=True,
                )
                await asyncio.to_thread(
                    mark_vacancy_sent_for_review,
                    vacancy.id,
                    message.message_id,
                )
        except HHAPIAccessDeniedError:
            logger.exception(
                "HH API denied or rate-limited access; automatic scanning is disabled"
            )
            return
        except Exception:
            logger.exception("Periodic public vacancy scan failed; will retry next interval")
        await asyncio.sleep(settings.hh_scan_interval_minutes * 60)


async def _start_periodic_scan(application: Application) -> None:
    application.bot_data["public_vacancy_scan_task"] = asyncio.create_task(
        _periodic_scan(application),
        name="public-vacancy-scan",
    )


async def _stop_periodic_scan(application: Application) -> None:
    task = application.bot_data.pop("public_vacancy_scan_task", None)
    if task is None:
        return
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
