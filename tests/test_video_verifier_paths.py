import sys
import unittest
from pathlib import Path
from unittest import mock

import video_verifier


class VideoVerifierPathTests(unittest.TestCase):
    def test_frozen_app_resolves_data_next_to_executable(self):
        executable = Path("C:/Program Files/YouTube Downloader Pro/YouTube Downloader Pro.exe")

        with mock.patch.object(sys, "frozen", True, create=True):
            with mock.patch.object(sys, "executable", str(executable)):
                self.assertEqual(
                    video_verifier.get_script_directory(),
                    str(executable.parent),
                )


if __name__ == "__main__":
    unittest.main()
