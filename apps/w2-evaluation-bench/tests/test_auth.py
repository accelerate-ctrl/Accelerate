"""Google Workspace session layer (server/auth.py): the zennify.com gate and
the HMAC session lifecycle. verify_google_credential is Google's signed-token
check (library-backed, network) — exercised live, not here; everything the
server DECIDES with its output is covered below."""
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import auth  # noqa: E402


class DomainGate(unittest.TestCase):
    def test_zennify_ok(self):
        self.assertTrue(auth.domain_ok("richard.odhiambo@zennify.com"))
        self.assertTrue(auth.domain_ok("A.User@Zennify.com".lower(), "zennify.com"))

    def test_hd_claim_must_match_when_present(self):
        self.assertTrue(auth.domain_ok("a@zennify.com", "zennify.com"))
        self.assertFalse(auth.domain_ok("a@zennify.com", "gmail.com"))

    def test_wrong_domain_rejected(self):
        for bad in ("me@gmail.com", "me@zennify.com.evil.io", "me@notzennify.com",
                    "@zennify.com", "", "me@zennify.como"):
            self.assertFalse(auth.domain_ok(bad), bad)

    def test_prototype_error_copy(self):
        self.assertIn("Zennify Workspace account", auth.DOMAIN_ERROR)
        self.assertIn("@zennify.com", auth.DOMAIN_ERROR)


class SessionLifecycle(unittest.TestCase):
    def test_roundtrip(self):
        t = auth.mint_session("sofia.reyes@zennify.com")
        self.assertEqual(auth.check_session(t), "sofia.reyes@zennify.com")

    def test_tamper_rejected(self):
        t = auth.mint_session("a@zennify.com")
        self.assertIsNone(auth.check_session(t[:-6] + "aaaaaa"))
        self.assertIsNone(auth.check_session("garbage"))
        self.assertIsNone(auth.check_session(""))

    def test_expiry(self):
        old = auth.mint_session("a@zennify.com",
                                now=time.time() - auth.SESSION_TTL_SECONDS - 5)
        self.assertIsNone(auth.check_session(old))
        fresh = auth.mint_session("a@zennify.com")
        self.assertIsNotNone(auth.check_session(fresh))


if __name__ == "__main__":
    unittest.main()
