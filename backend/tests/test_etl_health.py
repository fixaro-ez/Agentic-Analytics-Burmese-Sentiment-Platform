from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.services import etl


class EtlHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_reports_independent_unavailable_nodes(self):
        with (
            patch.object(
                etl,
                "_get_mongo_client",
                side_effect=RuntimeError("mongo offline"),
            ),
            patch.object(
                etl,
                "get_pool",
                new=AsyncMock(side_effect=RuntimeError("postgres offline")),
            ),
        ):
            result = await etl.get_health()

        nodes = {node.id: node for node in result.nodes}
        self.assertEqual(nodes["mongodb"].status, "unavailable")
        self.assertIn("mongo offline", nodes["mongodb"].error)
        self.assertEqual(nodes["postgresql"].status, "unavailable")
        self.assertIn("postgres offline", nodes["postgresql"].error)
        self.assertEqual(result.overall_status, "unavailable")
        self.assertEqual(len(result.loads), 3)


if __name__ == "__main__":
    unittest.main()
