import unittest

from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtGui import QIcon

from ui_script import DRIVE_ADD_ICON_PATH


class DriveToolbarIconTests(unittest.TestCase):
    def test_drive_add_svg_exists_and_is_valid(self):
        renderer = QSvgRenderer(DRIVE_ADD_ICON_PATH)
        icon = QIcon(DRIVE_ADD_ICON_PATH)

        self.assertTrue(renderer.isValid(), DRIVE_ADD_ICON_PATH)
        self.assertFalse(icon.isNull(), DRIVE_ADD_ICON_PATH)
        self.assertEqual(renderer.defaultSize().width(), 24)
        self.assertEqual(renderer.defaultSize().height(), 24)


if __name__ == "__main__":
    unittest.main()
