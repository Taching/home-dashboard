import unittest

from app.domain.activity_feed import ActivityFeedService


class ActivityFeedTests(unittest.TestCase):
    def test_dedupe_skips_repeat_key(self):
        feed = ActivityFeedService()
        feed.add_event("out", "notion", "sync 3 open tasks", dedupe_key="ready:3")
        feed.add_event("out", "notion", "sync 3 open tasks", dedupe_key="ready:3")
        feed.add_event("out", "notion", "sync 3 open tasks (refreshed)", dedupe_key="ready:3")
        feed.add_event("out", "notion", "sync 4 open tasks", dedupe_key="ready:4")

        events = feed.recent_events()
        self.assertEqual(len(events), 2)
        self.assertEqual(events[-1].detail, "sync 4 open tasks")

    def test_recent_events_respect_limit(self):
        feed = ActivityFeedService(maxlen=80)
        for index in range(5):
            feed.add_event("info", "dashboard", f"event {index}")
        self.assertEqual(len(feed.recent_events(3)), 3)


if __name__ == "__main__":
    unittest.main()
