import unittest
from dataclasses import replace
from unittest.mock import patch

from job_pipeline import hh_api
from job_pipeline.config import Settings


class FakeResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.headers = {}
        self.responses = iter(responses)
        self.post_calls = []
        self.get_calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return next(self.responses)

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs, dict(self.headers)))
        return next(self.responses)


class HHAPITests(unittest.TestCase):
    def setUp(self):
        self.settings = replace(
            Settings(),
            hh_client_id="test-client-id",
            hh_client_secret="test-client-secret",
            hh_user_agent="job-pipeline-tests/1.0 (contact: test@example.com)",
            hh_search_query="аналитик",
            hh_area=113,
            hh_per_page=2,
            hh_max_pages=1,
            hh_request_delay=1,
        )

    def test_fetches_and_normalizes_vacancies_using_application_token(self):
        session = FakeSession(
            [
                FakeResponse({"access_token": "test-access-token"}),
                FakeResponse(
                    {
                        "items": [
                            {
                                "id": "123",
                                "name": "Системный аналитик",
                                "employer": {"name": "Пример"},
                                "area": {"name": "Москва"},
                                "snippet": {
                                    "responsibility": "Собирать требования",
                                    "requirement": "Знать SQL",
                                },
                                "salary": {
                                    "from": 180000,
                                    "to": 240000,
                                    "currency": "RUR",
                                },
                            }
                        ]
                    }
                ),
            ]
        )

        with (
            patch.object(hh_api, "get_settings", return_value=self.settings),
            patch.object(hh_api.requests, "Session", return_value=session),
        ):
            vacancies = hh_api.fetch_public_vacancies()

        self.assertEqual(len(vacancies), 1)
        self.assertEqual(vacancies[0].title, "Системный аналитик")
        self.assertEqual(vacancies[0].employer_name, "Пример")
        self.assertEqual(vacancies[0].city, "Москва")
        self.assertEqual(vacancies[0].url, "https://hh.ru/vacancy/123")
        self.assertEqual(vacancies[0].description, "Собирать требования\nЗнать SQL")
        self.assertEqual(vacancies[0].salary, "180000–240000 RUR")
        self.assertEqual(
            session.post_calls[0][1]["data"],
            {
                "grant_type": "client_credentials",
                "client_id": "test-client-id",
                "client_secret": "test-client-secret",
            },
        )
        self.assertEqual(
            session.get_calls[0][2]["Authorization"],
            "Bearer test-access-token",
        )
        self.assertEqual(
            session.get_calls[0][1]["params"],
            {"text": "аналитик", "area": 113, "page": 0, "per_page": 2},
        )

    def test_fetches_full_description_from_api_for_hh_vacancy_url(self):
        session = FakeSession(
            [
                FakeResponse({"access_token": "test-access-token"}),
                FakeResponse(
                    {"description": "<p>Первое требование</p><p>Второе требование</p>"}
                ),
            ]
        )

        with (
            patch.object(hh_api, "get_settings", return_value=self.settings),
            patch.object(hh_api.requests, "Session", return_value=session),
            patch.object(hh_api.time, "sleep"),
        ):
            description = hh_api.fetch_public_vacancy_description(
                "https://hh.ru/vacancy/456?from=search"
            )

        self.assertEqual(description, "Первое требование\nВторое требование")
        self.assertEqual(
            session.get_calls[0][0],
            "https://api.hh.ru/vacancies/456",
        )

    def test_rejects_non_hh_vacancy_url_before_request(self):
        with self.assertRaisesRegex(ValueError, "hh.ru vacancy URL"):
            hh_api.fetch_public_vacancy_description("https://example.com/vacancy/456")

    def test_requires_both_application_credentials(self):
        settings_without_secret = replace(self.settings, hh_client_secret="")
        with (
            patch.object(hh_api, "get_settings", return_value=settings_without_secret),
            patch.object(hh_api.requests, "Session") as session_factory,
        ):
            with self.assertRaisesRegex(ValueError, "HH_CLIENT_ID and HH_CLIENT_SECRET"):
                hh_api.fetch_public_vacancies()
        session_factory.assert_not_called()

    def test_stops_without_retry_when_api_rate_limits_search(self):
        session = FakeSession(
            [
                FakeResponse({"access_token": "test-access-token"}),
                FakeResponse({}, status_code=429),
            ]
        )
        with (
            patch.object(hh_api, "get_settings", return_value=self.settings),
            patch.object(hh_api.requests, "Session", return_value=session),
        ):
            with self.assertRaises(hh_api.HHAPIAccessDeniedError):
                hh_api.fetch_public_vacancies()

        self.assertEqual(len(session.get_calls), 1)


if __name__ == "__main__":
    unittest.main()
