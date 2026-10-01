import importlib.util
import os
import sqlite3
import tempfile
import unittest
from unittest import mock


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
        self.assertEqual(self.server.RELEASE_VERSION, "0.2.45")
        self.assertIn('card("WINDOW SHARES"', self.server.HTML)
        self.assertNotIn("SHARES SINCE BLOCK", self.server.HTML)
        self.assertIn('id="neuralRain"', self.server.HTML)
        self.assertIn('id="neuralRainToggle"', self.server.HTML)
        self.assertIn("NEURAL RAIN · ONLINE", self.server.HTML)
        self.assertIn('const storageKey="terminusNeuralRain"', self.server.HTML)
        self.assertIn('localStorage.setItem(storageKey', self.server.HTML)
        self.assertIn('document.hidden', self.server.HTML)
        self.assertIn('@media(prefers-reduced-motion:reduce)', self.server.HTML)
        self.assertIn('id="nightwave"', self.server.HTML)
        self.assertIn('NIGHTWAVE // ONLY XBT ACCEPTED', self.server.HTML)
        self.assertIn('id="nightwaveAudio"', self.server.HTML)
        self.assertIn('const NIGHTWAVE_TRACKS=[', self.server.HTML)
        self.assertIn('initNightwave();', self.server.HTML)
        self.assertEqual(self.server.HTML.count('https://opengameart.org/sites/default/files/'), 5)
        self.assertTrue(any(
            "media-src 'self' https://opengameart.org" in value
            for value in self.server.Handler.send_security_headers.__code__.co_consts
            if isinstance(value, str)
        ))

    def test_quick_connect_places_prime_pubkey_below_datum_endpoint(self):
        endpoint_pos = self.server.HTML.index("datum.terminuspool.xyz:28915")
        quick_pubkey_pos = self.server.HTML.index('id="quickPrimePubkey"')
        pool_stats_pos = self.server.HTML.index('id="poolStats"')
        self.assertLess(endpoint_pos, quick_pubkey_pos)
        self.assertLess(quick_pubkey_pos, pool_stats_pos)
        self.assertIn('id="quickCopyPrimePubkey"', self.server.HTML)
        self.assertIn('/assets/datum-pool-setup.png', self.server.HTML)
        self.assertGreater(len(self.server.POOL_SETUP_PNG), 1000)
        self.assertIn("Sitemap: https://terminuspool.xyz/sitemap.xml", self.server.ROBOTS_TXT)
        self.assertIn("https://terminuspool.xyz/", self.server.SITEMAP_XML)
        self.assertIn("404 // SIGNAL LOST", self.server.NOT_FOUND_HTML)
        self.assertIn('id="windowBitcoin"', self.server.HTML)
        self.assertNotIn('class="sun"', self.server.HTML)
        self.assertNotIn("Math.pow(progressRatio", self.server.HTML)
        self.assertIn("const travel=mobileRise?75:210", self.server.HTML)
        self.assertIn("coin.dataset.visualProgress", self.server.HTML)
        self.assertIn("const blockEffort=d.blockEffort||{}", self.server.HTML)
        self.assertIn("legacyWindowProgress", self.server.HTML)
        self.assertIn("one statistically expected block", self.server.HTML)
        self.assertIn("TERMINUS BLOCK // VICTORY LAP", self.server.HTML)
        self.assertIn("blockEffort.celebrationActive===true", self.server.HTML)
        self.assertIn('class="daylightSky"', self.server.HTML)
        self.assertIn("--daylight-level", self.server.HTML)
        self.assertIn("hero.dataset.daylightProgress", self.server.HTML)
        self.assertIn("DAYBREAK RUN", self.server.HTML)
        self.assertEqual(self.server.HTML.count('data-pixel-style="32-bit"'), 2)
        self.assertIn("color:var(--gold);font-size:clamp(25px", self.server.HTML)
        self.assertIn('class="bitcoinSprite celestial32"', self.server.HTML)
        self.assertIn('class="bitcoinGlow"', self.server.HTML)
        self.assertIn('.hero[data-block-celebration="active"] .windowBitcoin', self.server.HTML)
        self.assertIn('transform:translateX(-50%) translateY(-48px) !important', self.server.HTML)
        self.assertIn('width:86px !important', self.server.HTML)
        self.assertIn('.hero[data-block-celebration="active"] .skyMoon', self.server.HTML)
        self.assertIn('TerminusPool est. block <strong>974025</strong>', self.server.HTML)
        self.assertNotIn("TERMINUS FOUND ITS FIRST BLOCK", self.server.HTML)
        self.assertNotIn('class="firstBlock"', self.server.HTML)
        self.assertIn("moonSprite", self.server.HTML)
        self.assertIn("skyMoonGlow", self.server.HTML)
        self.assertIn('class="roadsideLights"', self.server.HTML)
        self.assertEqual(self.server.HTML.count('class="roadLamp '), 6)
        self.assertEqual(self.server.HTML.count("pair1"), 2)
        self.assertEqual(self.server.HTML.count("pair2"), 3)
        self.assertEqual(self.server.HTML.count("pair3"), 3)
        self.assertIn("@keyframes roadLampLeft", self.server.HTML)
        self.assertIn("@keyframes roadLampRight", self.server.HTML)
        self.assertIn("55%{left:22%", self.server.HTML)
        self.assertIn("55%{left:78%", self.server.HTML)
        self.assertIn("55%{left:15%", self.server.HTML)
        self.assertIn("55%{left:85%", self.server.HTML)
        self.assertIn("--road-light-level:1", self.server.HTML)
        self.assertIn("opacity:var(--road-light-level)", self.server.HTML)
        self.assertIn('"--road-light-level"', self.server.HTML)
        self.assertIn("Math.max(.10,1-daylightLevel*.90)", self.server.HTML)
        self.assertIn('class="victoryPlane ltr"', self.server.HTML)
        self.assertIn('class="victoryPlane rtl"', self.server.HTML)
        self.assertEqual(self.server.HTML.count('class="planeTrack"'), 2)
        self.assertIn("@keyframes airplaneFlyRight", self.server.HTML)
        self.assertIn("@keyframes airplaneFlyLeft", self.server.HTML)
        self.assertIn(".victoryPlane.ltr .planeTrack{animation:airplaneFlyRight 90s linear 12s infinite}", self.server.HTML)
        self.assertIn(".victoryPlane.rtl .planeTrack{animation:airplaneFlyLeft 90s linear 57s infinite}", self.server.HTML)
        self.assertEqual(self.server.HTML.count('class="planeProp"'), 2)
        self.assertIn("@keyframes propellerSpin", self.server.HTML)
        self.assertIn("width:34px;height:16px", self.server.HTML)
        self.assertIn("width:22px;height:11px", self.server.HTML)
        self.assertEqual(self.server.HTML.count('viewBox="0 0 120 50"'), 2)
        self.assertEqual(self.server.HTML.count('class="planeBody"'), 2)
        self.assertEqual(self.server.HTML.count('class="planeWing"'), 2)
        self.assertEqual(self.server.HTML.count('class="planeCabin"'), 2)
        self.assertEqual(self.server.HTML.count('class="planeTail"'), 2)
        self.assertEqual(self.server.HTML.count('class="planeStrut"'), 2)
        self.assertEqual(self.server.HTML.count('class="planeWheelPant"'), 2)
        self.assertIn(".hero svg{\n  background:none;border:0", self.server.HTML)
        self.assertIn("20%{opacity:1;transform:translateX", self.server.HTML)
        self.assertIn('data-block-celebration="active"', self.server.HTML)
        self.assertEqual(self.server.HTML.count('class="towPickaxe"'), 2)
        self.assertEqual(self.server.HTML.count("<span>block found</span>"), 2)
        self.assertIn('.hero[data-block-celebration="active"] .towLine', self.server.HTML)
        self.assertIn(".victoryPlane.ltr{top:var(--plane-altitude,35%)", self.server.HTML)
        self.assertIn(".victoryPlane.rtl{top:var(--plane-altitude,39%)", self.server.HTML)
        self.assertIn("function initAirplaneFlybys()", self.server.HTML)
        self.assertIn('track.addEventListener("animationiteration"', self.server.HTML)
        self.assertIn('if(event.target!==track || event.animationName!==flightAnimation)return', self.server.HTML)
        self.assertIn('? "airplaneFlyLeft"', self.server.HTML)
        self.assertIn(': "airplaneFlyRight"', self.server.HTML)
        self.assertNotIn("planes.forEach(setRandomAltitude)", self.server.HTML)
        self.assertIn("Lock altitude for the full visible crossing", self.server.HTML)
        self.assertIn('plane.style.setProperty("--plane-altitude"', self.server.HTML)
        self.assertIn("plane.dataset.altitudeMinPx", self.server.HTML)
        self.assertIn("plane.dataset.altitudeMaxPx", self.server.HTML)
        self.assertIn("Math.min(...tips)", self.server.HTML)
        self.assertIn("spriteHeight*.34", self.server.HTML)
        self.assertIn("initAirplaneFlybys();", self.server.HTML)
        self.assertIn("position:absolute;z-index:3;width:164px;height:164px", self.server.HTML)
        self.assertNotIn("streetLightPair", self.server.HTML)
        self.assertIn('class="hitchhiker"', self.server.HTML)
        self.assertIn("@keyframes hitchhikerPass", self.server.HTML)
        self.assertIn("animation:hitchhikerPass 360s linear 180s infinite", self.server.HTML)
        self.assertIn("translate(245px,178px) scale(1.55)", self.server.HTML)
        self.assertNotIn("hitchhikerVisit", self.server.HTML)
        self.assertIn('class="hitchThumb"', self.server.HTML)
        self.assertIn('id="xbtMarket"', self.server.HTML)
        self.assertIn('id="xbtPrice"', self.server.HTML)
        self.assertIn("renderXbtMarket(d.xbtMarket)", self.server.HTML)
        self.assertIn("NEOXEX SYMBOL BTCB2", self.server.HTML)

    def test_neoxex_xbt_market_normalization(self):
        market = self.server.normalize_xbt_market({
            "success": True,
            "pair": "BTCB2_USDC",
            "ticker": {
                "lastPrice": 355,
                "changePercent": -3.527,
                "high24h": 400,
                "low24h": 320,
                "volume24h": 555.25,
                "quoteVolume24h": 202256.98,
                "trades24h": 1900,
                "computedAt": 1_800_000_000_000,
                "bestBid": 351.1,
                "bestAsk": 355,
            },
        }, now=1_800_000_030)
        self.assertEqual(market["pair"], "BTCB2_USDC")
        self.assertEqual(market["displayPair"], "XBT / USDC")
        self.assertEqual(market["lastPrice"], 355)
        self.assertEqual(market["trades24h"], 1900)
        self.assertFalse(market["stale"])

    def test_neoxex_xbt_market_rejects_invalid_price(self):
        with self.assertRaises(ValueError):
            self.server.normalize_xbt_market({
                "success": True,
                "ticker": {"lastPrice": 0},
            })

    def test_neoxex_xbt_market_uses_recent_cache_during_outage(self):
        self.server.XBT_MARKET_CACHE["data"] = {
            "available": True,
            "pair": "BTCB2_USDC",
            "lastPrice": 355,
            "stale": False,
        }
        self.server.XBT_MARKET_CACHE["fetchedAt"] = 1_000
        with mock.patch.object(
            self.server.urllib.request,
            "urlopen",
            side_effect=OSError("exchange unavailable"),
        ):
            market = self.server.load_xbt_market(now=1_031)
        self.assertTrue(market["available"])
        self.assertTrue(market["stale"])
        self.assertEqual(market["lastPrice"], 355)

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

    def test_block_effort_persists_and_resets_only_on_new_block(self):
        base = {
            "hashrate": 0.001,
            "poolMiners": 1,
            "connections": 1,
            "accepted": 0,
            "rejected": 0,
            "height": 974100,
            "difficulty": 1_000,
            "blocks": 1,
        }
        first = self.server.record_history(base, now=1_800_000_000)
        self.assertEqual(first["effortPercent"], 0)

        second = self.server.record_history(base, now=1_800_000_060)
        self.assertGreater(second["effortPercent"], 1)
        self.assertLess(second["effortPercent"], 2)

        restarted = load_server(self.temp.name)
        third = restarted.record_history(base, now=1_800_000_120)
        self.assertGreater(third["effortPercent"], second["effortPercent"])

        found = dict(base)
        found["blocks"] = 2
        found["lastBlockAt"] = 1_800_000_180
        reset = restarted.record_history(found, now=1_800_000_180)
        self.assertEqual(reset["effortPercent"], 0)
        self.assertEqual(reset["visualPercent"], 100)
        self.assertTrue(reset["celebrationActive"])
        self.assertEqual(reset["celebrationUntil"], 1_800_086_580)
        self.assertEqual(reset["observedBlocks"], 2)
        self.assertEqual(reset["lastResetAt"], 1_800_000_180)

        restarted_again = load_server(self.temp.name)
        during = restarted_again.record_history(
            found,
            now=1_800_000_240,
        )
        self.assertTrue(during["celebrationActive"])
        self.assertEqual(during["visualPercent"], 100)
        self.assertGreater(during["effortPercent"], 0)

        expired = restarted_again.record_history(
            found,
            now=1_800_086_580,
        )
        self.assertFalse(expired["celebrationActive"])
        self.assertEqual(
            expired["visualPercent"],
            min(100, expired["effortPercent"]),
        )

    def test_block_celebration_uses_exact_24_hour_boundary(self):
        found_at = 1_800_000_000
        active, until = self.server._block_celebration(
            found_at,
            found_at + 86_399,
        )
        self.assertTrue(active)
        self.assertEqual(until, found_at + 86_400)

        active, until = self.server._block_celebration(
            found_at,
            found_at + 86_400,
        )
        self.assertFalse(active)
        self.assertEqual(until, found_at + 86_400)

    def test_v0242_ignores_removed_cycle_share_columns(self):
        with tempfile.TemporaryDirectory() as state_dir:
            database = os.path.join(state_dir, "terminus-history.sqlite3")
            connection = sqlite3.connect(database)
            connection.execute(
                """
                CREATE TABLE block_effort_state (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    observed_blocks INTEGER NOT NULL,
                    estimated_work REAL NOT NULL,
                    estimated_shares REAL NOT NULL DEFAULT 0,
                    last_sample_at INTEGER NOT NULL,
                    last_hashrate_hs REAL NOT NULL,
                    last_share_difficulty REAL NOT NULL DEFAULT 0,
                    tracking_since INTEGER NOT NULL,
                    last_reset_at INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO block_effort_state VALUES
                (1, 1, 100, 25, 1800000000, 1000000000, 4, 1799999000, 1799999000)
                """
            )
            connection.commit()
            connection.close()

            server = load_server(state_dir)
            effort = server.record_history({
                "hashrate": 0.001,
                "poolMiners": 1,
                "connections": 1,
                "accepted": 0,
                "rejected": 0,
                "height": 974100,
                "difficulty": 1000,
                "blocks": 1,
            }, now=1800000060)
            self.assertGreater(effort["estimatedWork"], 100)
            self.assertNotIn("estimatedShares", effort)

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
