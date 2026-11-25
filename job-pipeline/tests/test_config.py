import os
import unittest
from unittest.mock import patch

from job_pipeline.config import Settings


class SettingsTests(unittest.TestCase):
    def test_demo_mode_requires_a_test_database_name(self):
        with patch.dict(os.environ, {"DB_NAME": "hh_automation"}, clear=False):
            with self.assertRaisesRegex(ValueError, "end with '_test'"):
                Settings(bot_demo_mode=True)

    def test_demo_mode_uses_test_database_instead_of_database_url(self):
        with patch.dict(
            os.environ,
            {
                "DB_NAME": "hh_automation_test",
                "DATABASE_URL": "sqlite:///production.db",
            },
            clear=False,
        ):
            settings = Settings(bot_demo_mode=True)

        self.assertIn("/hh_automation_test", settings.database_url)
        self.assertNotIn("production.db", settings.database_url)


if __name__ == "__main__":
    unittest.main()
