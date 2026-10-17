import unittest
from types import SimpleNamespace
from app.db.test_environment import check_test_target


class TestEnvironmentGuard(unittest.TestCase):
    def settings(self, **overrides):
        values = dict(APP_ENV="test", DATABASE_SCHEMA="ssp_test", TEST_DATABASE_PROJECT_REF="abcdefghijklmnopqrst", DATABASE_URL="postgresql://postgres.abcdefghijklmnopqrst:example@aws-0-test.pooler.supabase.com:5432/postgres")
        return SimpleNamespace(**(values | overrides))

    def test_accepts_only_the_selected_project(self):
        self.assertEqual(check_test_target(self.settings()).port, 5432)
        for change in [dict(APP_ENV="production"), dict(DATABASE_SCHEMA="public"), dict(TEST_DATABASE_PROJECT_REF="otherprojectreference"), dict(DATABASE_URL=""), dict(DATABASE_URL="postgresql://postgres:example@localhost:5432/postgres"), dict(DATABASE_URL="postgresql://postgres.abcdefghijklmnopqrst:example@aws-0-test.pooler.supabase.com:6543/postgres")]:
            with self.subTest(fields=list(change)), self.assertRaises(ValueError):
                check_test_target(self.settings(**change))


if __name__ == "__main__":
    unittest.main()
