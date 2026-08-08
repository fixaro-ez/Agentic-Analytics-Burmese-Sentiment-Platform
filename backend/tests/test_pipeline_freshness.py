from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from burmese_absa import clean_feedbacks as cleaning
from nlp import run_absa_pipeline as absa


class _Collection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, *_args, **_kwargs):
        return [dict(doc) for doc in self.docs]


class _Database:
    def __init__(self, collections):
        self.collections = {
            name: _Collection(docs) for name, docs in collections.items()
        }

    def __getitem__(self, name):
        return self.collections[name]


class CleaningFreshnessTests(unittest.TestCase):
    def test_new_and_changed_source_documents_are_pending(self):
        raw = {
            "_id": "post-1",
            "title_or_post": "New menu",
            "entity_name": "Example",
            "source_type": "Social",
            "post_timestamp": "2026-08-01",
            "reactions_breakdown": {"total": 10, "like": 8},
            "grouped_reactions": {"positivity_ratio": 0.8},
            "total_shares": 2,
            "total_comments": 3,
        }
        fingerprint = cleaning.source_fingerprint(
            raw, cleaning.CONTENT_SOURCE_FIELDS
        )
        db = _Database(
            {
                cleaning.CONTENTS_COLLECTION: [raw],
                cleaning.CLEANED_CONTENTS_COLLECTION: [
                    {"_id": "post-1", "source_fingerprint": fingerprint}
                ],
            }
        )

        self.assertEqual(
            cleaning.get_unprocessed_ids(
                cleaning.CONTENTS_COLLECTION,
                cleaning.CLEANED_CONTENTS_COLLECTION,
                db,
            ),
            set(),
        )

        raw["reactions_breakdown"]["total"] = 11
        self.assertEqual(
            cleaning.get_unprocessed_ids(
                cleaning.CONTENTS_COLLECTION,
                cleaning.CLEANED_CONTENTS_COLLECTION,
                db,
            ),
            {"post-1"},
        )


class AbsaFreshnessTests(unittest.TestCase):
    def test_retrained_model_contract_and_stage2_pair_format(self):
        aspect_model = SimpleNamespace(
            config=SimpleNamespace(num_labels=5)
        )
        sentiment_model = SimpleNamespace(
            config=SimpleNamespace(num_labels=3)
        )

        absa._validate_model_contract(aspect_model, sentiment_model)
        self.assertEqual(
            absa._sentiment_aspect_text("staff_and_service"),
            "staff and service",
        )

    def test_model_contract_rejects_legacy_six_label_checkpoint(self):
        legacy_model = SimpleNamespace(
            config=SimpleNamespace(num_labels=6)
        )

        with self.assertRaisesRegex(RuntimeError, "model has 6 outputs"):
            absa._validate_model_contract(legacy_model)

    def test_source_or_threshold_change_invalidates_absa_output(self):
        cleaned = {
            "_id": "post-1",
            "platform": "facebook",
            "cleaning_status": "clean",
            "cleaned_text": "New menu",
            "source_fingerprint": "source-v1",
        }
        processing_fingerprint = absa._processing_fingerprint(
            cleaned, pipeline="contents", threshold=0.5
        )
        db = _Database(
            {
                absa.CLEANED_CONTENTS: [cleaned],
                absa.OUTPUT_CONTENTS: [
                    {
                        "_id": "post-1",
                        "processing_fingerprint": processing_fingerprint,
                    }
                ],
            }
        )

        self.assertEqual(absa.get_pending_content_ids(db, 0.5), set())
        self.assertEqual(absa.get_pending_content_ids(db, 0.6), {"post-1"})

        cleaned["source_fingerprint"] = "source-v2"
        self.assertEqual(absa.get_pending_content_ids(db, 0.5), {"post-1"})


if __name__ == "__main__":
    unittest.main()
