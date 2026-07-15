import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import shutil
import time

from backend.modules.file_search.config import FileSearchConfig
from backend.modules.file_search.matcher import FileMatcher
from backend.modules.file_search.indexer import FileIndexer
from backend.modules.file_search.search_engine import SearchEngine
from backend.modules.file_search.intent_handler import FileSearchIntentHandler, InteractionState
from backend.modules.file_search.file_opener import FileOpener

class TestFileSearchConfig(unittest.TestCase):
    def test_default_config(self):
        config = FileSearchConfig()
        self.assertNotEqual(len(config.search_paths), 0)
        self.assertIn("Windows", config.excluded_paths)
        self.assertIn("pdf", config.supported_extensions)
        self.assertTrue(config.index_db_path.endswith(".db"))

class TestFileMatcher(unittest.TestCase):
    def setUp(self):
        self.matcher = FileMatcher(threshold=50.0)

    def test_pre_filter(self):
        # Match
        self.assertTrue(self.matcher.pre_filter("resume", "My Resume.pdf"))
        self.assertTrue(self.matcher.pre_filter("py notes", "python_notes.txt"))
        # No match
        self.assertFalse(self.matcher.pre_filter("resume", "tax_return.xlsx"))

    def test_exact_match_boost(self):
        # Exact stem match should score higher than substring match
        curr = time.time()
        score_exact = self.matcher.score_match("resume", "Resume.pdf", "pdf", curr, curr)
        score_sub = self.matcher.score_match("resume", "My Resume File.pdf", "pdf", curr, curr)
        self.assertGreater(score_exact, score_sub)

    def test_recency_boost(self):
        # Newer file should score higher than old file with same name similarity
        curr = time.time()
        score_new = self.matcher.score_match("resume", "Resume.pdf", "pdf", curr, curr)
        score_old = self.matcher.score_match("resume", "Resume.pdf", "pdf", curr - 10 * 86400, curr)
        self.assertGreater(score_new, score_old)

    def test_extension_boost(self):
        # Query ending in extension should boost candidate matching that extension
        curr = time.time()
        score_boosted = self.matcher.score_match("resume pdf", "Resume.pdf", "pdf", curr, curr)
        score_normal = self.matcher.score_match("resume pdf", "Resume.docx", "docx", curr, curr)
        self.assertGreater(score_boosted, score_normal)

class TestFileIndexer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_index.db"
        self.config = FileSearchConfig(
            search_paths=[self.temp_dir],
            index_db_path=str(self.db_path),
            supported_extensions=["txt", "pdf"],
            excluded_paths=[]
        )
        self.indexer = FileIndexer(self.config)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_db_initialization(self):
        conn = self.indexer._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_index'")
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "file_index")
        conn.close()

    def test_update_index(self):
        p1 = Path(self.temp_dir) / "Resume.pdf"
        p1.write_text("dummy content")
        
        p2 = Path(self.temp_dir) / "notes.txt"
        p2.write_text("dummy content")
        
        p3 = Path(self.temp_dir) / "image.png"
        p3.write_text("dummy content")

        self.indexer.update_index()
        files = self.indexer.get_all_files()
        
        filenames = [f.filename for f in files]
        self.assertIn("Resume.pdf", filenames)
        self.assertIn("notes.txt", filenames)
        self.assertNotIn("image.png", filenames)

class TestSearchEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_search.db"
        self.config = FileSearchConfig(search_paths=[], index_db_path=str(self.db_path))
        self.indexer = FileIndexer(self.config)
        self.matcher = FileMatcher(threshold=50.0)
        self.engine = SearchEngine(self.config, self.indexer, self.matcher)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch.object(FileIndexer, 'get_all_files')
    def test_search_ranking(self, mock_get_all_files):
        from backend.modules.file_search.indexer import IndexedFile
        curr = time.time()
        mock_get_all_files.return_value = [
            IndexedFile("/path/to/Resume.pdf", "Resume.pdf", "pdf", curr - 5*86400, 100),
            IndexedFile("/path/to/Resume_old.pdf", "Resume_old.pdf", "pdf", curr - 20*86400, 100),
            IndexedFile("/path/to/tax.xlsx", "tax.xlsx", "xlsx", curr, 100),
        ]
        
        results = self.engine.search("resume")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["filename"], "Resume.pdf")

class TestIntentHandler(unittest.TestCase):
    def setUp(self):
        self.engine = MagicMock(spec=SearchEngine)
        self.handler = FileSearchIntentHandler(self.engine)

    def test_intent_detection(self):
        self.assertTrue(self.handler.is_file_search_intent("Open resume"))
        self.assertTrue(self.handler.is_file_search_intent("Find my resume"))
        self.assertTrue(self.handler.is_file_search_intent("Search Python notes"))
        self.assertTrue(self.handler.is_file_search_intent("send resume to sunny on whatsapp"))
        self.assertTrue(self.handler.is_file_search_intent("whatsapp papa the tax bill"))
        self.assertFalse(self.handler.is_file_search_intent("What is the weather today?"))

        # Test parsing
        query, recipient = self.handler.parse_whatsapp_send("send my resume to jasleen")
        self.assertEqual(query, "resume")
        self.assertEqual(recipient, "jasleen")

    @patch("backend.modules.file_search.intent_handler.subprocess.run")
    @patch("backend.modules.file_search.intent_handler.webbrowser.open")
    def test_whatsapp_send_flow(self, mock_web_open, mock_sub_run):
        import os
        self.engine.search.return_value = [
            {"path": "/path/to/Resume.pdf", "filename": "Resume.pdf", "extension": "pdf", "modified_time": 0.0, "size": 10}
        ]
        # First command initiates the flow and since it's a single match, immediately sends it
        resp = self.handler.handle_command("send resume to sunny on whatsapp")
        self.assertIn("copied it to your clipboard", resp)
        self.assertIn("sunny", resp)
        
        abs_path = os.path.abspath("/path/to/Resume.pdf")
        self.assertTrue(mock_sub_run.call_count >= 2)
        mock_sub_run.assert_any_call(
            ["powershell.exe", "-Command", f"Set-Clipboard -LiteralPath '{abs_path}'"], check=True
        )
        mock_web_open.assert_called_once_with("https://web.whatsapp.com/")

    @patch("backend.modules.file_search.intent_handler.FileOpener.open_file")
    def test_handle_command_single_match(self, mock_open):
        self.engine.search.return_value = [
            {"path": "/path/to/Resume.pdf", "filename": "Resume.pdf", "extension": "pdf", "modified_time": 0.0, "size": 10}
        ]
        
        resp = self.handler.handle_command("Open resume")
        self.assertIn("Opening it", resp)
        self.assertEqual(self.handler.state, InteractionState.IDLE)
        mock_open.assert_called_once_with("/path/to/Resume.pdf")

    def test_handle_command_multiple_matches(self):
        self.engine.search.return_value = [
            {"path": "/path/to/Resume.pdf", "filename": "Resume.pdf", "extension": "pdf", "modified_time": 0.0, "size": 10},
            {"path": "/path/to/Resume_old.docx", "filename": "Resume_old.docx", "extension": "docx", "modified_time": 0.0, "size": 10}
        ]
        
        resp = self.handler.handle_command("Open resume")
        self.assertIn("Which one should I open?", resp)
        self.assertEqual(self.handler.state, InteractionState.AWAITING_SELECTION)
        self.assertEqual(len(self.handler.pending_candidates), 2)

    @patch("backend.modules.file_search.intent_handler.FileOpener.open_file")
    def test_selection_flow(self, mock_open):
        self.handler.state = InteractionState.AWAITING_SELECTION
        self.handler.pending_candidates = [
            {"path": "/path/to/Resume.pdf", "filename": "Resume.pdf", "extension": "pdf", "modified_time": 0.0, "size": 10},
            {"path": "/path/to/Resume_old.docx", "filename": "Resume_old.docx", "extension": "docx", "modified_time": 0.0, "size": 10}
        ]
        
        resp = self.handler.handle_command("second one")
        self.assertIn("Opening Resume_old.docx", resp)
        self.assertEqual(self.handler.state, InteractionState.IDLE)
        mock_open.assert_called_once_with("/path/to/Resume_old.docx")

if __name__ == "__main__":
    unittest.main()
