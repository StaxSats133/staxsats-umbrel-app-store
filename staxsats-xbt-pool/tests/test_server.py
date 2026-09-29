import importlib.util
import os
import tempfile
import unittest


SERVER_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "server.py"
)


def load_server(state_dir):
    os.environ["TERMINUS_STATE_DIR"] = state_dir
    os.environ["TERMINUS_ADMIN_ENABLED"] = "false"
    os.environ.pop("TERMINUS_TELEMETRY_MODE", None)
    os.environ.pop("TERMINUS_COLLECTOR_ENABLED", None)
    spec = importlib.util.spec_from_file_location("terminus_server", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TerminusServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = load_server(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_release_version_and_static_assets(self):
        self.assertEqual(self.server.RELEASE_VERSION, "0.2.21")
        self.assertIn("Sitemap: https://terminuspool.xyz/sitemap.xml", self.server.ROBOTS_TXT)
        self.assertIn("https://terminuspool.xyz/", self.server.SITEMAP_XML)
        self.assertIn("404 // SIGNAL LOST", self.server.NOT_FOUND_HTML)
        self.assertIn('id="windowBitcoin"', self.server.HTML)
        self.assertNotIn('class="sun"', self.server.HTML)
        self.assertIn("Math.pow(progressRatio,mobileRise?.45:.65)", self.server.HTML)
        self.assertIn("coin.dataset.visualProgress", self.server.HTML)
        self.assertIn(".skyMoon:before", self.server.HTML)
        self.assertIn("display:block !important", self.server.HTML)

    def test_window_work_progress_is_bounded(self):
        self.assertEqual(self.server.window_work_progress(0, 0), 0)
        self.assertEqual(self.server.window_work_progress(50, 100), 50)
        self.assertEqual(self.server.window_work_progress(100, 100), 100)
        self.assertEqual(self.server.window_work_progress(150, 100), 100)
        self.assertEqual(self.server.window_work_progress(-5, 100), 0)

    def test_history_summary_and_points(self):
        self.server.record_history({
            "hashrate": 12.5,
            "poolMiners": 2,
            "connections": 3,
            "accepted": 0,
            "rejected": 0,
            "height": 974025,
        })
        points, summary = self.server.load_history()
        self.assertEqual(len(points), 1)
        self.assertEqual(summary["samples"], 1)
        self.assertEqual(self.server.load_history_summary()["samples"], 1)

    def test_public_leaderboard_uses_opaque_aliases(self):
        identity = "bc1qexampleidentitythatmustneverleak"
        self.server.record_miner_activity([{
            "identity": identity,
            "tag": "TerminusPool",
            "hashrate_hs": 1_000_000_000_000,
            "work": 100,
            "best_share": 50,
        }], target_work=10_000)
        payload = self.server.load_public_leaderboard()
        rendered = str(payload)
        self.assertNotIn(identity, rendered)
        self.assertTrue(payload["miners"][0]["alias"].startswith("MINER-"))

    def test_admin_disabled_by_default(self):
        self.assertFalse(self.server.ADMIN_ENABLED)

    def test_community_install_uses_public_telemetry(self):
        self.assertFalse(self.server.OWNER_INSTANCE)
        self.assertFalse(self.server.LOCAL_TELEMETRY_ENABLED)
        self.assertFalse(self.server.COLLECTOR_ENABLED)

    def test_owner_marker_enables_local_telemetry(self):
        with tempfile.TemporaryDirectory() as state_dir:
            open(os.path.join(state_dir, "owner-admin.enabled"), "w").close()
            server = load_server(state_dir)
            self.assertTrue(server.OWNER_INSTANCE)
            self.assertTrue(server.LOCAL_TELEMETRY_ENABLED)
            self.assertTrue(server.COLLECTOR_ENABLED)


if __name__ == "__main__":
    unittest.main()
