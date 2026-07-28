import unittest

from fastapi.testclient import TestClient

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

    def test_entities_requires_auth(self):
        response = self.client.get("/api/entities")
        self.assertIn(response.status_code, [401, 403])

    def test_analytics_requires_auth(self):
        response = self.client.get("/api/analytics/overview")
        self.assertIn(response.status_code, [401, 403])

    def test_chat_requires_auth(self):
        response = self.client.post(
            "/api/chat/query",
            json={"question": "test"},
        )
        self.assertIn(response.status_code, [401, 403])


if __name__ == "__main__":
    unittest.main()
