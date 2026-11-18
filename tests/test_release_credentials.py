"""Release credentials must never follow a redirect to another service."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.request import Request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from github_release import GitHubRedirects, github_url, request


class ReleaseCredentialTests(unittest.TestCase):
    def test_untrusted_url_is_rejected_before_credentials_are_read(self):
        for url in ('https://example.com/upload', 'https://api.github.com@example.com/upload',
                    'http://api.github.com/upload', 'https://api.github.com.evil.invalid/upload'):
            with self.subTest(url=url), patch('github_release.subprocess.run') as credentials:
                with self.assertRaises(ValueError):
                    request('POST',url,payload={})
                credentials.assert_not_called()

    def test_authenticated_redirect_cannot_leave_github_api(self):
        handler=GitHubRedirects()
        original=Request('https://api.github.com/repos/example/repo',headers={'Authorization':'Bearer fixture'})
        with self.assertRaises(ValueError):
            handler.redirect_request(original,None,302,'redirect',{},'https://example.com/')
        self.assertEqual(github_url('https://uploads.github.com/repos/example/repo/assets'),
                         'https://uploads.github.com/repos/example/repo/assets')
