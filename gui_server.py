import os
import sys
import json
import logging
import webbrowser
import http.server
import socketserver
from pathlib import Path
from urllib.parse import urlparse
from backend.modules.file_search import FileSearchManager

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("FileSearch.GUIServer")

PORT = 8520  # Dedicated port for AION GUI
GUI_DIR = Path(__file__).parent / "frontend" / "dist"



class FileSearchHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=None, manager=None, **kwargs):
        self.manager = manager
        # Serve from the static gui/ directory
        super().__init__(*args, directory=str(GUI_DIR), **kwargs)

    def end_headers(self):
        # Enable CORS and disable cache during development/use
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed_path = urlparse(self.path)
        if parsed_path.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            # Fetch backend state
            state_name = self.manager.intent_handler.state.name
            candidates = self.manager.intent_handler.pending_candidates
            status_data = {
                "state": state_name,
                "candidates": [{
                    "filename": c["filename"],
                    "path": c["path"],
                    "extension": c.get("extension", ""),
                    "size": c.get("size", 0),
                    "score": c.get("score", 0)
                } for c in candidates]
            }
            self.wfile.write(json.dumps(status_data).encode("utf-8"))
            return
            
        # Delegate static file serving to SimpleHTTPRequestHandler
        super().do_GET()

    def do_POST(self):
        parsed_path = urlparse(self.path)
        if parsed_path.path == "/api/command":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            
            try:
                data = json.loads(post_data)
                command_text = data.get("command", "").strip()
            except Exception:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode("utf-8"))
                return

            logger.info(f"Received GUI command: '{command_text}'")
            
            # Route and execute search/selection/fallback
            response_text = self.manager.handle_command(command_text)
            
            # Retrieve updated state and candidates
            state_name = self.manager.intent_handler.state.name
            candidates = self.manager.intent_handler.pending_candidates
            
            result = {
                "response": response_text,
                "state": state_name,
                "candidates": [{
                    "filename": c["filename"],
                    "path": c["path"],
                    "extension": c.get("extension", ""),
                    "size": c.get("size", 0),
                    "score": c.get("score", 0)
                } for c in candidates]
            }
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

def run_server():
    logger.info("Initializing FileSearchManager...")
    manager = FileSearchManager()
    
    # Start background indexing
    manager.start()
    
    # Check if we have an index built. If not, trigger an initial update.
    indexed_files = manager.indexer.get_all_files()
    if not indexed_files:
        logger.info("First-time setup: Building file index database. This might take a few moments...")
        manager.indexer.update_index()
        logger.info(f"File index initialized. Total files: {len(manager.indexer.get_all_files())}")
    else:
        logger.info(f"Loaded existing index with {len(indexed_files)} files.")

    # Ensure the GUI directory exists
    if not GUI_DIR.exists():
        logger.error(f"GUI folder does not exist at {GUI_DIR}. Please make sure you created the index.html, style.css, and app.js inside it.")
        sys.exit(1)

    # Factory to inject the manager dependency into our custom HTTP handler
    def handler_factory(*args, **kwargs):
        return FileSearchHTTPRequestHandler(*args, manager=manager, **kwargs)

    # Use socketserver to set up a reuseable TCP server
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", PORT), handler_factory) as httpd:
            logger.info(f"--------------------------------------------------")
            logger.info(f"AION Voice Assistant serving at http://localhost:{PORT}")
            logger.info(f"Press Ctrl+C to terminate the server.")
            logger.info(f"--------------------------------------------------")
            
            # Automatically launch the web page
            if "--no-browser" not in sys.argv:
                webbrowser.open(f"http://localhost:{PORT}")

            
            httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("\nKeyboardInterrupt detected. Shutting down...")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
    finally:
        logger.info("Stopping background indexer thread...")
        manager.stop()
        logger.info("AION Assistant stopped cleanly.")

if __name__ == "__main__":
    run_server()
