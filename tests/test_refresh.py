"""Tests for repository change detection and Gemini file expiration tracking."""

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from modules import state
from modules.gemini import gemini_files_need_refresh
from modules.repos import repository_has_updates


class RefreshTests(unittest.TestCase):
    """Verify refresh decisions use remote commits and expiration margins."""

    def setUp(self):
        self.previous_files = state.UploadedFiles
        self.previous_expiration = state.GEMINI_FILES_EXPIRE_AT
        self.previous_repo_path = state.LOCAL_REPO_PATH
        self.previous_repo_url = state.REPO_URL
        state.UploadedFiles = []
        state.GEMINI_FILES_EXPIRE_AT = None

    def tearDown(self):
        state.UploadedFiles = self.previous_files
        state.GEMINI_FILES_EXPIRE_AT = self.previous_expiration
        state.LOCAL_REPO_PATH = self.previous_repo_path
        state.REPO_URL = self.previous_repo_url

    def test_missing_files_need_refresh(self):
        self.assertTrue(gemini_files_need_refresh())

    def test_files_refresh_inside_margin(self):
        now = datetime.now(timezone.utc)
        state.UploadedFiles = [SimpleNamespace(expiration_time=now + timedelta(hours=2))]
        state.GEMINI_FILES_EXPIRE_AT = now + timedelta(hours=2)

        self.assertFalse(gemini_files_need_refresh(now=now))
        self.assertTrue(gemini_files_need_refresh(now=now + timedelta(hours=1, seconds=1)))

    @patch("modules.repos.os.path.exists", return_value=True)
    @patch("modules.repos.git.Repo")
    def test_remote_commit_comparison(self, repo_factory, _exists):
        state.LOCAL_REPO_PATH = "sources"
        state.REPO_URL = "https://example.invalid/repo.git"
        repo = repo_factory.return_value
        repo.head.commit.hexsha = "local-commit"
        repo.git.ls_remote.return_value = "remote-commit\tHEAD"

        self.assertTrue(repository_has_updates())

        repo.git.ls_remote.return_value = "local-commit\tHEAD"
        self.assertFalse(repository_has_updates())


if __name__ == "__main__":
    unittest.main()