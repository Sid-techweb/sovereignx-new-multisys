import unittest
from unittest.mock import patch, MagicMock

from app.rag import resource_guard
from app.config import settings


class TestResourceGuard(unittest.TestCase):
    """
    Tests the Windows commit-headroom preflight signal. The investigation
    proved this (CommitLimit - CommittedBytes) predicts BGE-M3 crashes
    where free physical RAM alone does not, so these tests pin down the
    exact arithmetic and the safe/unsafe boundary rather than depending on
    the live machine's current memory state.
    """

    def _fake_stat(self, avail_phys_bytes, total_pagefile_bytes, avail_pagefile_bytes):
        stat = MagicMock()
        stat.ullAvailPhys = avail_phys_bytes
        stat.ullTotalPageFile = total_pagefile_bytes
        stat.ullAvailPageFile = avail_pagefile_bytes
        return stat

    @patch("app.rag.resource_guard._query_windows_memory")
    def test_safe_when_headroom_above_threshold(self, mock_query):
        # ~6.4GB headroom, matching the "stable" condition observed in investigation
        mock_query.return_value = self._fake_stat(
            avail_phys_bytes=6 * 1024**3,
            total_pagefile_bytes=27 * 1024**3,
            avail_pagefile_bytes=int(6.4 * 1024**3),
        )
        with patch.object(settings, "BGE_MIN_COMMIT_HEADROOM_MB", 2048):
            status = resource_guard.get_memory_status()

        self.assertTrue(status.safe_for_embedding)
        self.assertEqual(status.source, "windows_commit_charge")
        self.assertAlmostEqual(status.commit_headroom_mb, 6.4 * 1024, delta=1)

    @patch("app.rag.resource_guard._query_windows_memory")
    def test_unsafe_when_headroom_below_threshold(self, mock_query):
        # ~1GB headroom, matching the "crashing" condition observed in investigation
        mock_query.return_value = self._fake_stat(
            avail_phys_bytes=4 * 1024**3,
            total_pagefile_bytes=27 * 1024**3,
            avail_pagefile_bytes=int(1.0 * 1024**3),
        )
        with patch.object(settings, "BGE_MIN_COMMIT_HEADROOM_MB", 2048):
            status = resource_guard.get_memory_status()

        self.assertFalse(status.safe_for_embedding)
        self.assertAlmostEqual(status.commit_headroom_mb, 1.0 * 1024, delta=1)

    @patch("app.rag.resource_guard._query_windows_memory")
    def test_computed_committed_mb_matches_limit_minus_headroom(self, mock_query):
        mock_query.return_value = self._fake_stat(
            avail_phys_bytes=4 * 1024**3,
            total_pagefile_bytes=27475488768,  # exact value observed during investigation
            avail_pagefile_bytes=621043712,    # exact ~0.6GB headroom observed while crashing
        )
        status = resource_guard.get_memory_status()
        self.assertAlmostEqual(
            status.committed_mb, (27475488768 - 621043712) / (1024 * 1024), delta=0.01
        )

    @patch("app.rag.resource_guard._query_windows_memory", return_value=None)
    def test_falls_back_gracefully_when_windows_api_unavailable(self, mock_query):
        # Simulates non-Windows or a failed GlobalMemoryStatusEx call.
        status = resource_guard.get_memory_status()
        self.assertEqual(status.source, "fallback_available_ram")
        # Must not raise, and must still produce a usable safe_for_embedding verdict.
        self.assertIsInstance(status.safe_for_embedding, bool)

    def test_threshold_is_configurable_not_hardcoded(self):
        with patch("app.rag.resource_guard._query_windows_memory") as mock_query:
            mock_query.return_value = self._fake_stat(
                avail_phys_bytes=4 * 1024**3,
                total_pagefile_bytes=27 * 1024**3,
                avail_pagefile_bytes=int(1.5 * 1024**3),
            )
            with patch.object(settings, "BGE_MIN_COMMIT_HEADROOM_MB", 1024):
                status_low_threshold = resource_guard.get_memory_status()
            with patch.object(settings, "BGE_MIN_COMMIT_HEADROOM_MB", 4096):
                status_high_threshold = resource_guard.get_memory_status()

        self.assertTrue(status_low_threshold.safe_for_embedding)
        self.assertFalse(status_high_threshold.safe_for_embedding)


if __name__ == "__main__":
    unittest.main()
