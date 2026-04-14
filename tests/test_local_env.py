import os
import unittest
from pathlib import Path

from scripts.local_env import load_env_file, strip_env_quotes, update_env_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_TMP = PROJECT_ROOT / "data" / "private" / "test_tmp"


class LocalEnvTests(unittest.TestCase):
    def test_strip_env_quotes(self) -> None:
        self.assertEqual(strip_env_quotes('"value"'), "value")
        self.assertEqual(strip_env_quotes("'value'"), "value")
        self.assertEqual(strip_env_quotes("plain value"), "plain value")

    def test_load_env_file_does_not_override_existing_by_default(self) -> None:
        TEST_TMP.mkdir(parents=True, exist_ok=True)
        path = TEST_TMP / "load_env_sample.env"
        path.write_text("SAMPLE_KEY=file-value\nQUOTED_KEY='quoted value'\n", encoding="utf-8")

        os.environ["SAMPLE_KEY"] = "existing-value"
        try:
            loaded = load_env_file(path)
            self.assertEqual(loaded["SAMPLE_KEY"], "file-value")
            self.assertEqual(os.environ["SAMPLE_KEY"], "existing-value")
            self.assertEqual(os.environ["QUOTED_KEY"], "quoted value")
        finally:
            os.environ.pop("SAMPLE_KEY", None)
            os.environ.pop("QUOTED_KEY", None)

    def test_update_env_file_preserves_comments_and_sets_values(self) -> None:
        TEST_TMP.mkdir(parents=True, exist_ok=True)
        path = TEST_TMP / "update_env_sample.env"
        path.write_text("# hello\nSAMPLE_KEY=old\n", encoding="utf-8")

        try:
            update_env_file(path, {"SAMPLE_KEY": "new", "SECOND_KEY": "two"})

            self.assertEqual(path.read_text(encoding="utf-8"), "# hello\nSAMPLE_KEY=new\nSECOND_KEY=two\n")
            self.assertEqual(os.environ["SAMPLE_KEY"], "new")
            self.assertEqual(os.environ["SECOND_KEY"], "two")
        finally:
            os.environ.pop("SAMPLE_KEY", None)
            os.environ.pop("SECOND_KEY", None)


if __name__ == "__main__":
    unittest.main()
