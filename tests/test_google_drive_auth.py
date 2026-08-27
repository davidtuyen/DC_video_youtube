import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import google_drive_handler


class GoogleDriveAuthTests(unittest.TestCase):
    def test_packaged_oauth_client_is_found_from_executable_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir) / "YouTube Downloader Pro"
            data_dir = install_dir / "data"
            data_dir.mkdir(parents=True)
            packaged_client = data_dir / "google_drive_client.json"
            packaged_client.write_text(
                '{"installed":{"client_id":"team-app"}}', encoding="utf-8"
            )
            unrelated_cwd = Path(temp_dir) / "shortcut-working-directory"
            unrelated_cwd.mkdir()
            credentials = mock.Mock(valid=True)
            credentials.to_json.return_value = "{}"
            flow = mock.Mock()
            flow.run_local_server.return_value = credentials
            drive_service = object()

            previous_cwd = Path.cwd()
            try:
                os.chdir(unrelated_cwd)
                with mock.patch.object(sys, "frozen", True, create=True):
                    with mock.patch.object(
                        sys,
                        "executable",
                        str(install_dir / "YouTube Downloader Pro.exe"),
                    ):
                        with mock.patch.object(
                            google_drive_handler.InstalledAppFlow,
                            "from_client_secrets_file",
                            return_value=flow,
                        ) as create_flow:
                            with mock.patch.object(
                                google_drive_handler, "CustomAuthorizedSession", return_value=mock.Mock()
                            ):
                                with mock.patch.object(
                                    google_drive_handler, "build", return_value=drive_service
                                ):
                                    service, error = (
                                        google_drive_handler.authenticate_gdrive_user_flow(
                                            status_callback=lambda _message: None
                                        )
                                    )
            finally:
                os.chdir(previous_cwd)

            self.assertIs(service, drive_service)
            self.assertIsNone(error)
            create_flow.assert_called_once_with(
                str(packaged_client), google_drive_handler.SCOPES_DRIVE
            )


if __name__ == "__main__":
    unittest.main()
