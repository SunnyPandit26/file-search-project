import os
import logging
import google.generativeai as genai
from typing import Optional
from dotenv import load_dotenv

logger = logging.getLogger("AION.Brain")

class AIONBrain:
    def __init__(self, file_manager):
        self.file_manager = file_manager
        load_dotenv() # Load variables from .env file
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.model = None
        self.chat_session = None

        if self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                # Use Gemini 2.5 Flash for fast conversational responses
                self.model = genai.GenerativeModel(
                    'gemini-2.5-flash',
                    system_instruction="You are AION, a highly intelligent, sarcastic, and helpful AI voice assistant living on the user's Windows computer. Keep your answers concise, human-like, and conversational."
                )
                self.chat_session = self.model.start_chat(history=[])
                logger.info("AION Brain initialized successfully with Gemini API.")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini API: {e}")
        else:
            logger.warning("No GEMINI_API_KEY found in environment variables. AION Brain will run in fallback mode (only file/whatsapp commands).")

    def process_command(self, text: str) -> str:
        text = text.strip()
        if not text:
            return "I didn't hear anything."

        # 1. First, check if it's a specific system command (File Search or WhatsApp)
        # Or if we are in the middle of a file selection conversation
        if self.file_manager.is_file_search_intent(text):
            logger.info("Command routed to FileSearchManager.")
            return self.file_manager.handle_command(text)

        # 2. If not a system command, route to Gemini for conversational AI
        if self.chat_session:
            try:
                logger.info(f"Command routed to Gemini AI: {text}")
                response = self.chat_session.send_message(text)
                return response.text
            except Exception as e:
                logger.error(f"Gemini API error: {e}")
                return "I'm having trouble connecting to my AI brain right now."
        else:
            # Fallback if no API key
            return "I am AION, but my Gemini AI API key is not configured. I can currently only help you search for files or send WhatsApp messages."
