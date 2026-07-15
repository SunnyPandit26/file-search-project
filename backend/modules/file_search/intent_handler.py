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

    def _send_file_to_whatsapp(self, file_path: str, filename: str, recipient: str) -> str:
        import os
        import subprocess
        import webbrowser

        # 1. Copy physical file object to clipboard
        abs_path = os.path.abspath(file_path)
        logger.info(f"Copying file '{abs_path}' to Windows Clipboard...")
        copied = False
        try:
            # Escape single quotes for PowerShell
            escaped_path = abs_path.replace("'", "''")
            ps_cmd = f"Set-Clipboard -LiteralPath '{escaped_path}'"
            subprocess.run(["powershell.exe", "-Command", ps_cmd], check=True)
            copied = True
            logger.info("File copied to clipboard successfully.")
        except Exception as e:
            logger.error(f"Failed to copy file to clipboard: {e}")

        # 2. Look up contact number in local contacts.json
        recipient_clean = recipient.lower().strip()
        contacts_path = Path(__file__).parent.parent.parent.parent / "contacts.json"
        contacts = {}
        if contacts_path.exists():
            try:
                with open(contacts_path, "r", encoding="utf-8") as f:
                    contacts = json.load(f)
            except Exception:
                pass

        if not contacts:
            contacts = {
                "sunny": "+91XXXXXXXXXX",
                "papa": "+91XXXXXXXXXX",
                "mom": "+91XXXXXXXXXX",
                "jasleen": "+91XXXXXXXXXX"
            }
            try:
                with open(contacts_path, "w", encoding="utf-8") as f:
                    json.dump(contacts, f, indent=4)
            except Exception:
                pass

        phone = None
        for name_key, num in contacts.items():
            if name_key.lower() == recipient_clean:
                phone = num
                break

        # Check if we have a valid, non-placeholder phone number
        has_direct_phone = False
        if phone and "X" not in phone:
            clean_phone = re.sub(r"\D", "", phone)
            if clean_phone:
                has_direct_phone = True
                web_url = f"https://web.whatsapp.com/send?phone={clean_phone}"
        
        if not has_direct_phone:
            web_url = "https://web.whatsapp.com/"

        # Check if WhatsApp Web is already open in any browser window
        already_open = False
        try:
            check_cmd = 'Get-Process | Where-Object { $_.MainWindowTitle -like "*WhatsApp*" }'
            res = subprocess.run(["powershell.exe", "-Command", check_cmd], capture_output=True, text=True)
            already_open = "WhatsApp" in res.stdout
        except Exception:
            pass

        # 3. Define background automation worker
        search_term = phone if (phone and phone != "+91XXXXXXXXXX") else recipient
        delay_time = 3.0 if already_open else 15.0
        
        def worker():
            # Wait for WhatsApp Web page to load in the browser
            time.sleep(delay_time)
            
            if not copied:
                return

            # Clean search term to prevent SendKeys syntax errors
            clean_search = re.sub(r"[^a-zA-Z0-9\s\+]", "", search_term)

            if has_direct_phone:
                # Direct deep link: no search needed. Just focus, paste and send!
                ps_script = f"""
$sig = '
[DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
'
$type = Add-Type -MemberDefinition $sig -Name WindowAPI -PassThru

$wshell = New-Object -ComObject Wscript.Shell
$activated = $false

Write-Host "Searching for any window with 'WhatsApp' in the title..."
$proc = Get-Process | Where-Object {{ $_.MainWindowTitle -like "*WhatsApp*" }} | Select-Object -First 1

if ($proc) {{
    $hwnd = $proc.MainWindowHandle
    Write-Host "Found window: $($proc.MainWindowTitle) (HWND: $hwnd)"
    if ($hwnd -ne [IntPtr]::Zero) {{
        # Simulate Alt tap to unlock foreground
        $type::keybd_event(0x12, 0, 0, 0)
        $type::keybd_event(0x12, 0, 2, 0)
        
        # Immediately tap Escape to dismiss Chrome menu focus
        $type::keybd_event(0x1B, 0, 0, 0)
        $type::keybd_event(0x1B, 0, 2, 0)
        
        if ($type::IsIconic($hwnd)) {{
            $null = $type::ShowWindow($hwnd, 9) # SW_RESTORE
        }}
        $success = $type::SetForegroundWindow($hwnd)
        
        $wshell.AppActivate($proc.Id) | Out-Null
        $activated = $true
    }}
}}

if ($activated) {{
    Write-Host "WhatsApp window activated. Waiting 3 seconds for message input to focus..."
    Start-Sleep -Milliseconds 3000
    
    # Paste file from clipboard via keybd_event (0x11 = Ctrl, 0x56 = V)
    $type::keybd_event(0x11, 0, 0, 0) # Ctrl down
    $type::keybd_event(0x56, 0, 0, 0) # V down
    Start-Sleep -Milliseconds 100
    $type::keybd_event(0x56, 0, 2, 0) # V up
    $type::keybd_event(0x11, 0, 2, 0) # Ctrl up
    Start-Sleep -Milliseconds 2000
    
    # Send
    $wshell.SendKeys("{{ENTER}}")
    Write-Host "Keystrokes sent successfully."
}} else {{
    Write-Host "Error: Could not find or activate window with title containing 'WhatsApp'."
}}
"""
            else:
                # Generic link: search by name
                ps_script = f"""
$sig = '
[DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
'
$type = Add-Type -MemberDefinition $sig -Name WindowAPI -PassThru

$wshell = New-Object -ComObject Wscript.Shell
$activated = $false

Write-Host "Searching for any window with 'WhatsApp' in the title..."
$proc = Get-Process | Where-Object {{ $_.MainWindowTitle -like "*WhatsApp*" }} | Select-Object -First 1

if ($proc) {{
    $hwnd = $proc.MainWindowHandle
    Write-Host "Found window: $($proc.MainWindowTitle) (HWND: $hwnd)"
    if ($hwnd -ne [IntPtr]::Zero) {{
        # Simulate Alt tap to unlock foreground
        $type::keybd_event(0x12, 0, 0, 0)
        $type::keybd_event(0x12, 0, 2, 0)
        
        # Immediately tap Escape to dismiss Chrome menu focus
        $type::keybd_event(0x1B, 0, 0, 0)
        $type::keybd_event(0x1B, 0, 2, 0)
        
        if ($type::IsIconic($hwnd)) {{
            $null = $type::ShowWindow($hwnd, 9) # SW_RESTORE
        }}
        $success = $type::SetForegroundWindow($hwnd)
        
        $wshell.AppActivate($proc.Id) | Out-Null
        $activated = $true
    }}
}}

if ($activated) {{
    Write-Host "WhatsApp window activated successfully. Waiting 1.5 seconds..."
    Start-Sleep -Milliseconds 1500
    
    # Send Ctrl+Alt+/ via keybd_event (0x11 = Ctrl, 0x12 = Alt, 0xBF = OEM_2 / slash)
    $type::keybd_event(0x11, 0, 0, 0) # Ctrl down
    $type::keybd_event(0x12, 0, 0, 0) # Alt down
    $type::keybd_event(0xBF, 0, 0, 0) # Slash down
    Start-Sleep -Milliseconds 100
    $type::keybd_event(0xBF, 0, 2, 0) # Slash up
    $type::keybd_event(0x12, 0, 2, 0) # Alt up
    $type::keybd_event(0x11, 0, 2, 0) # Ctrl up
    Start-Sleep -Milliseconds 1200
    
    # Clear search
    $wshell.SendKeys("^a")
    Start-Sleep -Milliseconds 300
    $wshell.SendKeys("{{BACKSPACE}}")
    Start-Sleep -Milliseconds 400
    
    # Type contact name or phone
    $wshell.SendKeys("{clean_search}")
    Start-Sleep -Milliseconds 2500
    
    # Enter to open chat
    $wshell.SendKeys("{{ENTER}}")
    Start-Sleep -Milliseconds 2000
    
    # Paste file from clipboard via keybd_event (0x11 = Ctrl, 0x56 = V)
    $type::keybd_event(0x11, 0, 0, 0) # Ctrl down
    $type::keybd_event(0x56, 0, 0, 0) # V down
    Start-Sleep -Milliseconds 100
    $type::keybd_event(0x56, 0, 2, 0) # V up
    $type::keybd_event(0x11, 0, 2, 0) # Ctrl up
    Start-Sleep -Milliseconds 2000
    
    # Send
    $wshell.SendKeys("{{ENTER}}")
    Write-Host "Keystrokes sent successfully."
}} else {{
    Write-Host "Error: Could not find or activate window with title containing 'WhatsApp'."
}}
"""

            try:
                result = subprocess.run(
                    ["powershell.exe", "-Command", ps_script],
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info(f"WhatsApp Web automation PowerShell stdout:\n{result.stdout}")
                if result.stderr:
                    logger.warning(f"WhatsApp Web automation PowerShell stderr:\n{result.stderr}")
            except subprocess.CalledProcessError as e:
                logger.error(f"WhatsApp Web keystroke automation failed with exit code {e.returncode}")
                logger.error(f"Stdout:\n{e.stdout}")
                logger.error(f"Stderr:\n{e.stderr}")
            except Exception as e:
                logger.error(f"WhatsApp Web keystroke automation error: {e}")

        # 4. Trigger WhatsApp Web via webbrowser
        self._reset_state()
        logger.info(f"Launching WhatsApp Web in browser: {web_url}")

        try:
            webbrowser.open(web_url)
        except Exception as e:
            logger.error(f"Failed to launch WhatsApp Web URL: {e}")
        
        # Start background automation thread
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()
        
        if copied:
            return f"I found {filename}. I've copied it to your clipboard and opened WhatsApp Web. I will search for {recipient} and send it automatically in a few seconds."
        else:
            return f"I found {filename} and opened WhatsApp Web, but could not copy the file to your clipboard."

    def _reset_state(self):
        self.state = InteractionState.IDLE
        self.pending_candidates.clear()
        self.pending_query = ""
        self.is_whatsapp_action = False
        self.whatsapp_recipient = ""
