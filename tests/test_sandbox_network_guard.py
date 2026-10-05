"""run_code cannot reach internal addresses through georest.

Everything under site-packages counts as trusted library code -- which
includes georest, a complete HTTP client with no SSRF policy. Verified
2026-10-05 with the sandbox on: ``georest.restesri._http.fetch_json`` from
run_code fetched http://127.0.0.1:8899/ and returned it, and a request to
169.254.169.254 got as far as the network. geeViz.esriLib refuses both
(``geeViz._ssrf.check_url``), but nothing made a direct georest call do
the same. The sandbox's socket.connect hook now refuses link-local for
all sandboxed code and applies esriLib's policy to connects made from
georest code -- at the connect, so DNS rebinding and redirects are
covered too.

No listener is needed: a refused connect raises the sandbox's message;
one that got through would fail with an OS network error instead.
"""
import unittest

from geeViz.tests.test_sandbox_trust import _run_under_sandbox


def _fetch(url):
    return (
        "from georest.restesri import _http\n"
        f"_http.fetch_json({url!r}, timeout=5)\n"
    )


class GeorestCannotReachInternalAddresses(unittest.TestCase):
    def _assert_sandbox_refused(self, code, needle):
        result, out = _run_under_sandbox(code)
        self.assertIn("BLOCKED", result, out[-2000:])
        self.assertIn(needle, out, out[-2000:])

    def test_loopback_is_refused(self):
        self._assert_sandbox_refused(_fetch("http://127.0.0.1:9/x"),
                                     "georest may not connect to 127.0.0.1")

    def test_private_network_is_refused(self):
        self._assert_sandbox_refused(_fetch("http://10.0.0.1:9/x"),
                                     "georest may not connect to 10.0.0.1")

    def test_cloud_metadata_is_refused(self):
        self._assert_sandbox_refused(
            _fetch("http://169.254.169.254/computeMetadata/v1/"),
            "link-local addresses serve cloud metadata")


if __name__ == "__main__":
    unittest.main()
