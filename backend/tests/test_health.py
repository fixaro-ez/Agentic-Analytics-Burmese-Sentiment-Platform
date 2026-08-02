import unittest

from fastapi.testclient import TestClient

from app.auth import AuthUser, get_current_user
from app.main import app


class TestHealthEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_check(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "burmese-sentiment-api")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertIn("camera=()", response.headers["permissions-policy"])

    def test_entities_requires_auth(self):
        response = self.client.get("/api/entities")
        self.assertIn(response.status_code, [401, 403])

    def test_analytics_requires_auth(self):
        response = self.client.get("/api/analytics/overview")
        self.assertIn(response.status_code, [401, 403])

    def test_retired_impact_routes_are_not_exposed(self):
        paths = app.openapi()["paths"]
        self.assertNotIn("/api/analytics/impact", paths)
        self.assertFalse(
            any("campaign-classifications" in path for path in paths),
            "Retired campaign-classification routes must not be exposed.",
        )
        self.assertIn("/api/analytics/benchmark", paths)

    def test_chat_requires_auth(self):
        response = self.client.post(
            "/api/chat/query",
            json={"question": "test"},
        )
        self.assertIn(response.status_code, [401, 403])

    def test_etl_health_requires_auth(self):
        response = self.client.get("/api/etl/health")
        self.assertIn(response.status_code, [401, 403])

    def test_scrape_management_requires_auth(self):
        for path in (
            "/api/scraping/entities",
            "/api/scraping/schedules",
            "/api/scraping/history",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertIn(response.status_code, [401, 403])

    def test_cookie_upload_rejects_oversized_file(self):
        app.dependency_overrides[get_current_user] = lambda: AuthUser(
            "00000000-0000-0000-0000-000000000001",
            "qa@example.com",
            "authenticated",
        )
        try:
            response = self.client.post(
                "/api/scraping/cookies",
                files={"file": ("cookies.json", b"x" * (1024 * 1024 + 1), "application/json")},
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        self.assertEqual(response.status_code, 413)
        self.assertIn("1 MB", response.json()["detail"])

    def test_analytics_rejects_unknown_aspect(self):
        app.dependency_overrides[get_current_user] = lambda: AuthUser(
            "00000000-0000-0000-0000-000000000001",
            "qa@example.com",
            "authenticated",
        )
        try:
            response = self.client.get(
                "/api/analytics/reviews/flagged?aspect=not-a-real-aspect"
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
