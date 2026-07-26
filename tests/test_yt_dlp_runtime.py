import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import main_logic


class YtDlpJavaScriptRuntimeArgsTests(unittest.TestCase):
    def _runtime_args(self, available):
        builder = getattr(main_logic, "get_yt_dlp_js_runtime_args", None)
        self.assertIsNotNone(builder, "main_logic must provide JS runtime arguments")
        with TemporaryDirectory() as temp_dir:
            return builder(
                lambda name: available.get(name),
                base_dir=temp_dir,
            )

    def test_prefers_deno_when_available(self):
        args = self._runtime_args({
            "deno": r"C:\tools\deno.exe",
            "node": r"C:\Program Files\nodejs\node.exe",
        })

        self.assertEqual(args, ["--js-runtimes", r"deno:C:\tools\deno.exe"])

    def test_prefers_bundled_node_over_runtimes_on_path(self):
        builder = getattr(main_logic, "get_yt_dlp_js_runtime_args", None)
        self.assertIsNotNone(builder, "main_logic must provide JS runtime arguments")

        with TemporaryDirectory() as temp_dir:
            node_path = Path(temp_dir) / "data" / "node" / "node.exe"
            node_path.parent.mkdir(parents=True)
            node_path.touch()

            args = builder(
                lambda name: {"deno": r"C:\tools\deno.exe"}.get(name),
                base_dir=temp_dir,
            )

        self.assertEqual(args, ["--js-runtimes", f"node:{node_path}"])

    def test_uses_node_when_deno_is_unavailable(self):
        args = self._runtime_args({
            "node": r"C:\Program Files\nodejs\node.exe",
        })

        self.assertEqual(
            args,
            ["--js-runtimes", r"node:C:\Program Files\nodejs\node.exe"],
        )

    def test_adds_no_option_when_no_supported_runtime_is_installed(self):
        self.assertEqual(self._runtime_args({}), [])


if __name__ == "__main__":
    unittest.main()
