import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from job_pipeline.gemini_client import generate_demo_cover_letter
from job_pipeline.models import ApplicationEvent, Base, GeneratedLetter, Vacancy
from job_pipeline.workflow import get_latest_letter, record_status, require_positive_rating


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.vacancy = Vacancy(
            title="Системный аналитик",
            employer_name="Пример",
            url="https://hh.ru/vacancy/test",
            description="Требования к вакансии",
        )
        self.session.add(self.vacancy)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_records_status_event(self):
        record_status(
            self.session,
            self.vacancy.id,
            "liked",
            "Пользователь оценил вакансию положительно",
        )
        self.session.commit()

        self.assertEqual(self.vacancy.status, "liked")
        event = self.session.execute(select(ApplicationEvent)).scalar_one()
        self.assertEqual(event.status, "liked")

    def test_rejects_unknown_status(self):
        with self.assertRaises(ValueError):
            record_status(self.session, self.vacancy.id, "applied")

    def test_letter_requires_positive_rating(self):
        with self.assertRaisesRegex(ValueError, "only be generated after"):
            require_positive_rating(self.vacancy)
        self.vacancy.status = "liked"
        require_positive_rating(self.vacancy)

    def test_returns_latest_letter_for_vacancy(self):
        letter = GeneratedLetter(vacancy_id=self.vacancy.id, letter_text="Черновик")
        self.session.add(letter)
        self.session.commit()

        self.assertEqual(get_latest_letter(self.session, self.vacancy.id).letter_text, "Черновик")

    def test_requires_existing_letter(self):
        with self.assertRaisesRegex(ValueError, "No generated cover letter"):
            get_latest_letter(self.session, self.vacancy.id)

    def test_demo_letter_is_saved_without_external_generation(self):
        self.vacancy.status = "liked"
        self.session.commit()
        test_session_factory = sessionmaker(bind=self.engine)
        with patch("job_pipeline.gemini_client.SessionLocal", test_session_factory):
            letter = generate_demo_cover_letter(self.vacancy.id)

        self.assertEqual(letter.model_name, "demo")
        self.assertIn("ТЕСТОВЫЙ ЧЕРНОВИК", letter.letter_text)
        self.session.expire_all()
        self.assertEqual(self.vacancy.status, "letter_ready")
        event = self.session.execute(
            select(ApplicationEvent).where(ApplicationEvent.status == "letter_ready")
        ).scalar_one()
        self.assertIn("Gemini не вызывался", event.note)


if __name__ == "__main__":
    unittest.main()
