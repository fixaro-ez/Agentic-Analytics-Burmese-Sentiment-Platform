import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock

# The repository does not declare/install runtime dependencies in this environment.
playwright = types.ModuleType('playwright')
playwright_sync = types.ModuleType('playwright.sync_api')
playwright_sync.sync_playwright = MagicMock()
sys.modules.setdefault('playwright', playwright)
sys.modules.setdefault('playwright.sync_api', playwright_sync)
pymongo = types.ModuleType('pymongo')
pymongo.MongoClient = MagicMock
pymongo.UpdateOne = MagicMock
pymongo.ASCENDING = 1
pymongo.DESCENDING = -1
sys.modules.setdefault('pymongo', pymongo)

scraping = importlib.import_module('scraping')
ingest = importlib.import_module('ingest_to_mongo')


class FakeResponse:
    def __init__(self, url, payload, ok=True):
        self.url, self.payload, self.ok = url, payload, ok
    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeCard:
    def __init__(self, data): self.data = data
    def evaluate(self, _script): return self.data


class FakeLocator:
    def __init__(self, items=None, texts=None, visible=True, count_override=None):
        self.items, self.texts = items or [], texts or []
        self.visible = visible
        self.count_override = count_override
        self.last = self
    @property
    def first(self):
        return self.items[0] if self.items else self
    def count(self):
        if self.count_override is not None:
            return self.count_override
        return len(self.items) if self.items else len(self.texts)
    def nth(self, index): return self.items[index]
    def all_text_contents(self): return self.texts
    def filter(self, **_kwargs): return self
    def locator(self, _selector): return self
    def evaluate(self, _script): return False
    def is_visible(self): return self.visible
    def wait_for(self, **_kwargs): return None
    def inner_text(self): return self.texts[0] if self.texts else ''


class DomPage:
    def __init__(self, cards=None, modal_open=True):
        if cards is None:
            cards = [FakeCard({
                'id': 'r1', 'text': ' Great meal ', 'author': 'Ada',
                'date': '3 weeks ago',
            })]
        self.cards = cards
        self.modal_open = modal_open

    def locator(self, selector):
        if selector == scraping.FOODPANDA_REVIEW_MODAL:
            modal = FakeLocator(items=[FakeLocator(items=self.cards)], visible=self.modal_open)
            return modal
        if selector == scraping.FOODPANDA_REVIEW_CARDS:
            return FakeLocator(items=self.cards)
        return FakeLocator()


class FoodpandaUnitTests(unittest.TestCase):
    def setUp(self):
        scraping.session_data.clear()

    def test_reviews_url_normalization(self):
        base = 'https://www.foodpanda.com.mm/en/restaurant/t3kt/ykko-waizayandar'
        self.assertEqual(
            scraping.foodpanda_reviews_url(base),
            f'{base}/reviews')
        self.assertEqual(
            scraping.foodpanda_reviews_url(f'{base}/reviews'),
            f'{base}/reviews')

    def test_nested_api_discovery_rejects_message(self):
        payload = {'message':'not a review', 'data': {'items': [
            {'reviewId':'9', 'comment':' Tasty ', 'rating':4, 'userName':'Lin'}]}}
        self.assertEqual(scraping.find_foodpanda_review_objects(payload), [{
            'id':'9', 'author':'Lin', 'date':'', 'rating':4, 'text':'Tasty'}])

    def test_response_filter_error_and_dedup(self):
        state = {'records': []}
        response = FakeResponse('https://x/reviews', {'items':[{'id':'1','text':'Good','stars':5}]})
        scraping.collect_foodpanda_review_response(response, state)
        scraping.collect_foodpanda_review_response(response, state)
        scraping.collect_foodpanda_review_response(FakeResponse('https://x/reviews', ValueError()), state)
        scraping.collect_foodpanda_review_response(FakeResponse('https://x/menu', {'id':'2','text':'No','stars':1}), state)
        self.assertEqual(len(state['records']), 1)
        self.assertEqual(state['response_errors'], 1)

    def test_dom_fallback_extracts_fields(self):
        stats = {}
        with unittest.mock.patch.object(scraping, 'is_foodpanda_modal_open', return_value=True), \
             unittest.mock.patch.object(scraping, 'foodpanda_review_modal_locator',
                                        lambda page: page.locator(scraping.FOODPANDA_REVIEW_MODAL).first):
            records = scraping.mounted_foodpanda_reviews(DomPage(), stats)
        self.assertEqual(records[0]['text'], 'Great meal')
        self.assertEqual(records[0]['author'], 'Ada')
        self.assertIsNone(records[0].get('rating'))
        self.assertEqual(stats['dom_records'], 1)
        self.assertEqual(stats['legacy_nodes'], 0)

    def test_ui_chrome_rejection(self):
        self.assertFalse(scraping.is_real_foodpanda_review(
            {'text': 'Top reviews', 'author': 'Hnin', 'date': '1 week ago'}, source='dom'))
        self.assertFalse(scraping.is_real_foodpanda_review(
            {'text': 'All Ratings (5000+)', 'author': 'Hnin', 'date': '1 week ago'}, source='dom'))
        self.assertTrue(scraping.is_real_foodpanda_review(
            {'text': 'Very good', 'author': 'Kyaw', 'date': '1 week ago', 'rating': 5}, source='dom'))

    def test_api_record_requires_author_and_date(self):
        self.assertFalse(scraping.is_real_foodpanda_review(
            {'text': 'Tasty', 'author': 'Lin', 'date': '', 'rating': 4}, source='api'))
        self.assertTrue(scraping.is_real_foodpanda_review(
            {'text': 'Tasty', 'author': 'Lin', 'date': '2 days ago', 'rating': 4}, source='api'))

    def test_legacy_fallback_not_used(self):
        stats = {}
        page = DomPage(cards=[], modal_open=True)
        with unittest.mock.patch.object(scraping, 'is_foodpanda_modal_open', return_value=True), \
             unittest.mock.patch.object(scraping, 'foodpanda_review_modal_locator',
                                        lambda p: p.locator(scraping.FOODPANDA_REVIEW_MODAL).first):
            records = scraping.mounted_foodpanda_reviews(page, stats)
        self.assertEqual(records, [])
        self.assertEqual(stats['legacy_nodes'], 0)

    def test_overall_rating_extraction(self):
        page = DomPage()
        page.locator = lambda selector: (
            FakeLocator(texts=['4.9'], visible=True)
            if selector == scraping.FOODPANDA_REVIEW_MODAL
            else FakeLocator(items=[FakeLocator(items=page.cards)], visible=page.modal_open)
        )
        with unittest.mock.patch.object(scraping, 'is_foodpanda_modal_open', return_value=True), \
             unittest.mock.patch.object(scraping, 'foodpanda_review_modal_locator',
                                        lambda p: FakeLocator(texts=['4.9'], visible=True, items=[
                                            FakeLocator(texts=['4.9'])
                                        ])):
            rating = scraping.extract_foodpanda_overall_rating(page)
        self.assertEqual(rating, 4.9)

    def test_harvest_omits_per_feedback_rating(self):
        content = {'feedbacks': []}
        record = {'text': 'Good food', 'author': 'Kyaw', 'date': '1 week ago'}
        scraping.harvest_foodpanda_records(content, [record], set(), 'shop')
        self.assertNotIn('rating', content['feedbacks'][0])

    def test_identity_and_duplicate_count(self):
        by_id = {'id':'abc', 'text':'Same', 'author':'Ada', 'date':'3 weeks ago', 'rating':5}
        self.assertEqual(scraping.foodpanda_review_id('shop', by_id), 'fp_rev_abc')
        without_id = dict(by_id, id='')
        self.assertEqual(scraping.foodpanda_review_id('shop', without_id),
                         scraping.foodpanda_review_id('shop', without_id))
        content = {'feedbacks': []}
        seen = set()
        self.assertEqual(scraping.harvest_foodpanda_records(content, [by_id, by_id], seen, 'shop'), 1)
        self.assertEqual(len(content['feedbacks']), 1)
        self.assertEqual(content['feedbacks'][0]['raw_text'], 'Same')

    def test_entity_fallback(self):
        page = MagicMock()
        page.title.return_value = 'Nice Place | foodpanda'
        self.assertEqual(scraping.derive_foodpanda_entity_name('', page, 'https://x/shop/nice-place'), 'Nice Place')

    def test_empty_scrape_diagnostics_and_listener_cleanup(self):
        page = MagicMock()
        page.url = 'https://x/shop/empty'
        page.title.return_value = 'Empty | foodpanda'
        page.locator.return_value = FakeLocator()
        with unittest.mock.patch.object(scraping, 'is_foodpanda_modal_open', return_value=False), \
             unittest.mock.patch.object(scraping, 'foodpanda_review_modal_locator',
                                        lambda p: p.locator.return_value):
            result = scraping.scrape_foodpanda_reviews(page, page.url, '')
        self.assertEqual(result['review_diagnostics']['reason'], 'no_review_records_detected')
        self.assertEqual(result['review_diagnostics']['strategy'], 'dom-first')
        self.assertEqual(result['review_diagnostics']['pagination']['termination_reason'], 'end_of_list')
        page.remove_listener.assert_called_once()

    def test_pagination_safety_limit(self):
        page = MagicMock()
        page.locator.return_value = FakeLocator()
        with unittest.mock.patch.object(scraping, 'mounted_foodpanda_reviews', return_value=[]), \
             unittest.mock.patch.object(scraping, 'is_foodpanda_modal_open', return_value=True), \
             unittest.mock.patch.object(scraping, 'foodpanda_review_modal_locator',
                                        lambda page: page.locator(scraping.FOODPANDA_REVIEW_MODAL).first), \
             unittest.mock.patch.object(scraping, 'foodpanda_dom_signature', return_value='x'), \
             unittest.mock.patch.object(scraping, '_foodpanda_scroll_reviews_modal', return_value=True):
            result = scraping.exhaust_foodpanda_reviews(page, {'feedbacks':[]}, set(), 's', {'records':[]}, {}, max_steps=1)
        self.assertEqual(result['termination_reason'], 'safety_limit')

    def test_ingest_overall_rating_on_content(self):
        db = {'contents': MagicMock(), 'feedbacks': MagicMock()}
        db['contents'].find.return_value = []
        db['contents'].bulk_write.return_value = MagicMock(upserted_count=1, modified_count=0)
        db['feedbacks'].bulk_write.return_value = MagicMock(upserted_count=1, modified_count=0)
        import tempfile, json, os
        fd, path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        captured = []
        def capture_update(query, update, upsert=False):
            captured.append((query, update, upsert))
            return (query, update, upsert)
        try:
            with open(path, 'w', encoding='utf-8') as handle:
                json.dump([{'source_content_id':'shop','overall_rating':4.9,'feedbacks':[{
                    'source_feedback_id':'fp_rev_1','raw_text':'Good'}]}], handle)
            with unittest.mock.patch.object(ingest, 'UpdateOne', side_effect=capture_update), \
                 unittest.mock.patch('builtins.print'):
                self.assertEqual(ingest.ingest_json_file(db, path), (1, 1))
            content_updates = [value for value in captured if value[0].get('_id') == 'shop']
            feedback_updates = [value for value in captured if value[0].get('_id') == 'fp_rev_1']
            self.assertEqual(content_updates[0][1]['$set']['overall_rating'], 4.9)
            self.assertNotIn('rating', feedback_updates[0][1]['$set'])
        finally:
            os.unlink(path)


if __name__ == '__main__':
    unittest.main()
