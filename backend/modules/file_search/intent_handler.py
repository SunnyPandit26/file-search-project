import logging
import re
import json
import subprocess
import webbrowser
import threading
import os
import time
from enum import Enum, auto
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from .search_engine import SearchEngine
from .file_opener import FileOpener

logger = logging.getLogger("FileSearch.IntentHandler")

class InteractionState(Enum):
    IDLE = auto()
    AWAITING_SELECTION = auto()
    AWAITING_FULL_DRIVE_SEARCH = auto()

class FileSearchIntentHandler:
    def __init__(self, search_engine: SearchEngine):
        self.search_engine = search_engine
        self.state = InteractionState.IDLE
        self.pending_candidates: List[Dict[str, Any]] = []
        self.pending_query: str = ""
        self.is_whatsapp_action = False
        self.whatsapp_recipient = ""

        # Precompiled regex for intents
        # Match verbs like open, find, search, locate, optionally followed by helper words like "file named", "my", "the"
        self.intent_regex = re.compile(
            r"^(?:open\s+the\s+file\s+named|open\s+file|open\s+my|open\s+the|open|"
            r"find\s+the\s+file\s+named|find\s+file|find\s+my|find\s+the|find|"
            r"search\s+for\s+the\s+file\s+named|search\s+for\s+image|search\s+for|search\s+my|search|"
            r"locate\s+the\s+file\s+named|locate\s+file|locate)\s+(.+)$",
            re.IGNORECASE
        )

    def parse_whatsapp_send(self, text: str) -> Optional[Tuple[str, str]]:
        """
        Parses a whatsapp send command.
        Returns: (file_query, recipient_name) if matched, otherwise None.
        """
        text_clean = text.strip()
        patterns = [
            r"^(?:send|share|whatsapp)\s+(.+?)\s+(?:to|with)\s+(.+?)\s+on\s+whatsapp$",
            r"^(?:send|share|whatsapp)\s+(.+?)\s+on\s+whatsapp\s+(?:to|with)\s+(.+?)$",
            r"^(?:send|share|whatsapp)\s+(.+?)\s+(?:to|with)\s+(.+?)$",
            r"^whatsapp\s+(.+?)\s+the\s+(.+?)$",
            r"^whatsapp\s+(.+?)\s+(.+?)$"
        ]
        
        for pattern in patterns:
            match = re.match(pattern, text_clean, re.IGNORECASE)
            if match:
                if "whatsapp" in pattern and not ("to" in pattern or "with" in pattern):
                    recipient = match.group(1).strip()
                    file_query = match.group(2).strip()
                else:
                    file_query = match.group(1).strip()
                    recipient = match.group(2).strip()
                
                # Clean up helper words from file query
                file_query = re.sub(r"^(?:my|the|file|document|image)\s+", "", file_query, flags=re.IGNORECASE).strip()
                return file_query, recipient
                
        return None

    def is_file_search_intent(self, text: str) -> bool:
        """Determines if the text contains a file search command or a WhatsApp command."""
        text_clean = text.strip()
        # If we are not idle, we are in a conversation flow and must intercept the input
        if self.state != InteractionState.IDLE:
            return True
        if self.intent_regex.match(text_clean):
            return True
        if self.parse_whatsapp_send(text_clean):
            return True
        return False

    def handle_command(self, user_input: str) -> str:
        """Processes user voice commands and returns the assistant's voice/text response."""
        user_input_clean = user_input.strip()
        logger.info(f"Processing command in state {self.state.name}: '{user_input_clean}'")

        if self.state == InteractionState.AWAITING_SELECTION:
            return self._handle_selection(user_input_clean)
        
        elif self.state == InteractionState.AWAITING_FULL_DRIVE_SEARCH:
            return self._handle_full_drive_search_confirmation(user_input_clean)
            
        else: # IDLE state
            whatsapp_parse = self.parse_whatsapp_send(user_input_clean)
            if whatsapp_parse:
                file_query, recipient = whatsapp_parse
                self.is_whatsapp_action = True
                self.whatsapp_recipient = recipient
                query = file_query
            else:
                match = self.intent_regex.match(user_input_clean)
                if match:
                    query = match.group(1).strip()
                else:
                    query = user_input_clean

            if not query:
                return "What file would you like me to find?"

            return self._execute_search(query)

    def _execute_search(self, query: str) -> str:
        self.pending_query = query
        try:
            results = self.search_engine.search(query)
        except Exception as e:
            logger.error(f"Error during search: {e}", exc_info=True)
            return f"An error occurred while searching for the file: {e}"

        if not results:
            self.state = InteractionState.AWAITING_FULL_DRIVE_SEARCH
            return "I couldn't find that file. Would you like me to search the entire drive?"

        if len(results) == 1:
            # Single match - open or send
            candidate = results[0]
            if self.is_whatsapp_action:
                return self._send_file_to_whatsapp(candidate["path"], candidate["filename"], self.whatsapp_recipient)
            try:
                FileOpener.open_file(candidate["path"])
                logger.info(f"Opened single match: {candidate['path']}")
                return f"I found {candidate['filename']}. Opening it."
            except Exception as e:
                return f"I found {candidate['filename']}, but couldn't open it: {e}"

        # Multiple matches - ask for confirmation
        # Keep up to 5 best matches
        self.pending_candidates = results[:5]
        self.state = InteractionState.AWAITING_SELECTION
        
        response_lines = [f"I found {len(results)} files."]
        for idx, item in enumerate(self.pending_candidates, 1):
            response_lines.append(f"{idx}. {item['filename']}")
        
        question = "Which one should I send?" if self.is_whatsapp_action else "Which one should I open?"
        response_lines.append(question)
        
        return "\n".join(response_lines)

    def _handle_selection(self, user_input: str) -> str:
        # Check for cancel keywords
        if user_input.lower() in ["cancel", "none", "neither", "no", "stop", "exit"]:
            self._reset_state()
            return "Okay, cancelled."

        # Parse index
        idx = self._parse_ordinal_or_number(user_input, len(self.pending_candidates))
        if idx is not None:
            chosen = self.pending_candidates[idx]
            if self.is_whatsapp_action:
                return self._send_file_to_whatsapp(chosen["path"], chosen["filename"], self.whatsapp_recipient)
            try:
                FileOpener.open_file(chosen["path"])
                logger.info(f"Opened chosen file: {chosen['path']}")
                self._reset_state()
                return f"Opening {chosen['filename']}."
            except Exception as e:
                self._reset_state()
                return f"Could not open {chosen['filename']}: {e}"

        # If user typed or spoke a filename, we can try to matches against the candidate list
        # E.g. "Resume Final.pdf" matching "Resume Final.pdf"
        best_candidate = None
        best_match_len = 0
        user_input_lower = user_input.lower()
        for candidate in self.pending_candidates:
            cand_name_lower = candidate["filename"].lower()
            if user_input_lower == cand_name_lower or user_input_lower == Path(cand_name_lower).stem:
                best_candidate = candidate
                break
            # substring check as fallback
            if user_input_lower in cand_name_lower:
                if len(user_input_lower) > best_match_len:
                    best_candidate = candidate
                    best_match_len = len(user_input_lower)

        if best_candidate:
            if self.is_whatsapp_action:
                return self._send_file_to_whatsapp(best_candidate["path"], best_candidate["filename"], self.whatsapp_recipient)
            try:
                FileOpener.open_file(best_candidate["path"])
                logger.info(f"Opened best candidate by name match: {best_candidate['path']}")
                self._reset_state()
                return f"Opening {best_candidate['filename']}."
            except Exception as e:
                self._reset_state()
                return f"Could not open {best_candidate['filename']}: {e}"

        # If we couldn't match, ask again
        return f"I couldn't understand that choice. Please say the number (1 to {len(self.pending_candidates)}) or say cancel."

    def _handle_full_drive_search_confirmation(self, user_input: str) -> str:
        user_input_lower = user_input.lower()
        if user_input_lower in ["yes", "yeah", "y", "sure", "ok", "please", "do it"]:
            # Run full drive search
            logger.info(f"Executing full drive search for '{self.pending_query}'")
            try:
                results = self.search_engine.search_full_drive(self.pending_query)
            except Exception as e:
                logger.error(f"Error during full drive search: {e}", exc_info=True)
                self._reset_state()
                return f"An error occurred during full drive search: {e}"

            if not results:
                self._reset_state()
                return "I still couldn't find any matching files on the drive."

            if len(results) == 1:
                candidate = results[0]
                if self.is_whatsapp_action:
                    return self._send_file_to_whatsapp(candidate["path"], candidate["filename"], self.whatsapp_recipient)
                try:
                    FileOpener.open_file(candidate["path"])
                    self._reset_state()
                    return f"I found {candidate['filename']} on the drive. Opening it."
                except Exception as e:
                    self._reset_state()
                    return f"I found {candidate['filename']}, but couldn't open it: {e}"

            self.pending_candidates = results[:5]
            self.state = InteractionState.AWAITING_SELECTION
            
            response_lines = [f"I found {len(results)} files on the drive."]
            for idx, item in enumerate(self.pending_candidates, 1):
                response_lines.append(f"{idx}. {item['filename']}")
            
            question = "Which one should I send?" if self.is_whatsapp_action else "Which one should I open?"
            response_lines.append(question)
            return "\n".join(response_lines)
            
        else:
            self._reset_state()
            return "Okay, search cancelled."

    def _parse_ordinal_or_number(self, text: str, num_candidates: int) -> Optional[int]:
        text_lower = text.strip().lower()
        
        # Word mappings
        mapping = {
            "first": 0, "1st": 0, "one": 0, "number one": 0,
            "second": 1, "2nd": 1, "two": 1, "number two": 1, "second one": 1,
            "third": 2, "3rd": 2, "three": 2, "number three": 2, "third one": 2,
            "fourth": 3, "4th": 3, "four": 3, "number four": 3,
            "fifth": 4, "5th": 4, "five": 4, "number five": 4,
            "last": num_candidates - 1, "last one": num_candidates - 1
        }
        
        if text_lower in mapping:
            val = mapping[text_lower]
            if 0 <= val < num_candidates:
                return val

        # Try to find digits
        match = re.search(r"\b\d+\b", text_lower)
        if match:
            val = int(match.group(0)) - 1
            if 0 <= val < num_candidates:
                return val

        return None

def escape_sendkeys_text(text: str) -> str:
    replacements = {
        "~": "{~}",
        "+": "{+}",
        "^": "{^}",
        "%": "{%}",
        "(": "{(}",
        ")": "{)}",
        "{": "{{}",
        "}": "{}}",
        "[": "{[}",
        "]": "{]}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)

    def _send_file_to_whatsapp(self, file_path: str, filename: str, recipient: str) -> str:
        import os
        import subprocess
        import time
        import webbrowser

        # 1. Copy physical file object to Windows Clipboard
        abs_path = os.path.abspath(file_path)
        logger.info(f"Copying file '{abs_path}' to Windows Clipboard...")
        try:
            escaped_path = abs_path.replace("'", "''")
            ps_cmd = f"Set-Clipboard -LiteralPath '{escaped_path}'"
            subprocess.run(["powershell.exe", "-Command", ps_cmd], check=True)
            logger.info("File copied to clipboard successfully.")
        except Exception as e:
            logger.error(f"Failed to copy file to clipboard: {e}")

        # 2. Open WhatsApp Web
        logger.info("Opening WhatsApp Web in browser...")
        webbrowser.open("https://web.whatsapp.com/")

        # 3. Prepare safe recipient name for SendKeys
        safe_name = escape_sendkeys_text(recipient)

        # 4. Background thread for SendKeys automation
        def worker():
            ps_script = f'''
$wshell = New-Object -ComObject WScript.Shell

Start-Sleep -Seconds 10

$null = $wshell.AppActivate("WhatsApp")
Start-Sleep -Milliseconds 2000

$wshell.SendKeys("^%/")
Start-Sleep -Milliseconds 2000

$wshell.SendKeys("{safe_name}")
Start-Sleep -Milliseconds 2500

$wshell.SendKeys("{{ENTER}}")
Start-Sleep -Milliseconds 2500

$wshell.SendKeys("^v")
Start-Sleep -Milliseconds 2500

$wshell.SendKeys("{{ENTER}}")
'''
            try:
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", ps_script],
                    check=True
                )
                logger.info(f"Successfully sent '{filename}' to '{recipient}' via WhatsApp Web.")
            except Exception as e:
                logger.error(f"WhatsApp Web automation error: {e}")

        self._reset_state()
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()

        return f"I found {filename}. Opening WhatsApp Web to search for {recipient} and send it."


    def _reset_state(self):
        self.state = InteractionState.IDLE
        self.pending_candidates.clear()
        self.pending_query = ""
        self.is_whatsapp_action = False
        self.whatsapp_recipient = ""
