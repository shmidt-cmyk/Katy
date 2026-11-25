from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .config import Settings, get_settings

API_URL = "https://api.hh.ru"
TOKEN_URL = f"{API_URL}/token"
REQUEST_TIMEOUT = 30


class HHAPIError(RuntimeError):
    pass


class HHAPIAccessDeniedError(HHAPIError):
    pass


@dataclass(frozen=True)
class VacancyData:
    title: str
    employer_name: str
    city: str
    url: str
    description: str
    salary: str


def _client_credentials(settings: Settings) -> tuple[str, str]:
    client_id = settings.hh_client_id.strip()
    client_secret = settings.hh_client_secret.strip()
    if not client_id or not client_secret:
        raise ValueError("HH_CLIENT_ID and HH_CLIENT_SECRET must both be configured")
    return client_id, client_secret


def _check_response(response: requests.Response, operation: str) -> None:
    if response.status_code in {403, 429}:
        raise HHAPIAccessDeniedError(
            f"HH API rejected {operation} with HTTP {response.status_code}; stopping without retry"
        )
    if response.status_code >= 400:
        raise HHAPIError(f"HH API {operation} failed with HTTP {response.status_code}")


def _authorize(session: requests.Session, settings: Settings) -> None:
    client_id, client_secret = _client_credentials(settings)
    response = session.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=REQUEST_TIMEOUT,
    )
    _check_response(response, "application authorization")
    response.raise_for_status()
    token_data = response.json()
    access_token = token_data.get("access_token") if isinstance(token_data, dict) else None
    if not isinstance(access_token, str) or not access_token.strip():
        raise HHAPIError("HH API authorization response did not contain an access token")
    session.headers["Authorization"] = f"Bearer {access_token}"


def _api_get(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
    _check_response(response, "request")
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise HHAPIError("HH API returned an invalid JSON object")
    return data


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


def _salary_text(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    salary_from = value.get("from")
    salary_to = value.get("to")
    currency = value.get("currency")
    amount = ""
    if salary_from is not None and salary_to is not None:
        amount = f"{salary_from}–{salary_to}"
    elif salary_from is not None:
        amount = f"от {salary_from}"
    elif salary_to is not None:
        amount = f"до {salary_to}"
    if amount and isinstance(currency, str) and currency:
        amount = f"{amount} {currency}"
    return amount


def _vacancy_from_api(item: dict[str, Any]) -> VacancyData:
    vacancy_id = item.get("id")
    title = item.get("name")
    if not isinstance(vacancy_id, (str, int)) or not str(vacancy_id).isdigit():
        raise HHAPIError("HH API vacancy response has no valid vacancy ID")
    if not isinstance(title, str) or not title.strip():
        raise HHAPIError(f"HH API vacancy {vacancy_id} has no title")

    employer = item.get("employer")
    area = item.get("area")
    snippet = item.get("snippet")
    description_parts = []
    if isinstance(snippet, dict):
        for field in ("responsibility", "requirement"):
            text = _text(snippet.get(field))
            if text and text not in description_parts:
                description_parts.append(text)

    return VacancyData(
        title=title.strip()[:255],
        employer_name=_text(employer.get("name")) if isinstance(employer, dict) else "",
        city=_text(area.get("name")) if isinstance(area, dict) else "",
        url=f"https://hh.ru/vacancy/{vacancy_id}",
        description="\n".join(description_parts),
        salary=_salary_text(item.get("salary")),
    )


def fetch_public_vacancies() -> list[VacancyData]:
    settings = get_settings()
    if settings.hh_max_pages < 1:
        raise ValueError("HH_MAX_PAGES must be at least 1")
    if not 1 <= settings.hh_per_page <= 100:
        raise ValueError("HH_PER_PAGE must be between 1 and 100")
    if settings.hh_request_delay < 1:
        raise ValueError("HH_REQUEST_DELAY must be at least 1 second")
    if not settings.hh_user_agent.strip():
        raise ValueError("HH_USER_AGENT must not be empty")
    _client_credentials(settings)

    vacancies: list[VacancyData] = []
    with requests.Session() as session:
        session.headers.update(
            {
                "User-Agent": settings.hh_user_agent,
                "Accept": "application/json",
            }
        )
        _authorize(session, settings)
        for page in range(settings.hh_max_pages):
            if page:
                time.sleep(settings.hh_request_delay)
            data = _api_get(
                session,
                f"{API_URL}/vacancies",
                params={
                    "text": settings.hh_search_query,
                    "area": settings.hh_area,
                    "page": page,
                    "per_page": settings.hh_per_page,
                },
            )
            items = data.get("items")
            if not isinstance(items, list):
                raise HHAPIError("HH API vacancy search response has no items list")
            if any(not isinstance(item, dict) for item in items):
                raise HHAPIError("HH API vacancy search response contains an invalid item")
            vacancies.extend(
                _vacancy_from_api(item) for item in items
            )
            if len(items) < settings.hh_per_page:
                break
    return vacancies


def fetch_public_vacancy_description(url: str) -> str:
    parsed_url = urlparse(url)
    match = re.fullmatch(r"/vacancy/(\d+)/?", parsed_url.path)
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname not in {"hh.ru", "www.hh.ru"}
        or match is None
    ):
        raise ValueError("Expected a public hh.ru vacancy URL")

    settings = get_settings()
    if settings.hh_request_delay < 1:
        raise ValueError("HH_REQUEST_DELAY must be at least 1 second")
    if not settings.hh_user_agent.strip():
        raise ValueError("HH_USER_AGENT must not be empty")
    _client_credentials(settings)

    with requests.Session() as session:
        session.headers.update(
            {
                "User-Agent": settings.hh_user_agent,
                "Accept": "application/json",
            }
        )
        _authorize(session, settings)
        time.sleep(settings.hh_request_delay)
        data = _api_get(session, f"{API_URL}/vacancies/{match.group(1)}")
    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        raise HHAPIError("HH API vacancy response did not contain a description")
    text = BeautifulSoup(description, "html.parser").get_text("\n", strip=True)
    if not text:
        raise HHAPIError("HH API vacancy description was empty")
    return text
