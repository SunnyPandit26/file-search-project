import os
import json
import logging
import google.generativeai as genai
from typing import Optional
from dotenv import load_dotenv
from .system_tools import aion_tools, aion_tool_map, ollama_tool_definitions

logger = logging.getLogger("AION.Brain")

SYSTEM_PROMPT = (
    "You are AION, a highly intelligent, sarcastic, and helpful AI voice assistant "
    "living on the user's Windows computer. Keep your answers concise, human-like, "
    "and conversational. Use the provided tools autonomously whenever the user asks "
    "you to perform a system task like opening apps, creating files, searching YouTube, etc. "
    "CRITICAL: When the user asks you to write code, create a file, or create a script, you MUST call "
    "the `create_code_file` tool to save the code to a file. DO NOT output the code as text in your conversational response. "
    "Always write fully complete, working, and copy-pasteable code inside the tool."
)

class AIONBrain:
    def __init__(self, file_manager):
        self.file_manager = file_manager
        load_dotenv()  # Load variables from .env file
        self.gemini_key = os.getenv("GEMINI_API_KEY", "")
        self.groq_key = os.getenv("GROQ_API_KEY", "")

        # Groq state (Primary if available)
        self.groq_client = None
        self.groq_model = "llama-3.3-70b-versatile"
        self.groq_history = []
        self.groq_available = False

        # Gemini state (Secondary if Groq is active)
        self.gemini_model = None
        self.gemini_chat = None
        self.gemini_available = False

        # Ollama state (Fallback)
        self.ollama_available = False
        self.ollama_model = "qwen2.5-coder:7b"
        self.ollama_history = []

        # ── Initialize Groq (Primary) ───────────────────────────
        if self.groq_key:
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=self.groq_key)
                self.groq_available = True
                logger.info(f"AION Brain: Groq initialized successfully (PRIMARY, model={self.groq_model}).")
            except Exception as e:
                logger.error(f"Failed to initialize Groq API: {e}")
        else:
            logger.warning("No GROQ_API_KEY found. Groq will not be available.")

        # ── Initialize Gemini (Secondary/Alternative) ───────────
        if self.gemini_key:
            try:
                genai.configure(api_key=self.gemini_key)
                self.gemini_model = genai.GenerativeModel(
                    'gemini-1.5-flash',
                    tools=aion_tools,
                    system_instruction=SYSTEM_PROMPT
                )
                self.gemini_chat = self.gemini_model.start_chat(
                    history=[], enable_automatic_function_calling=True
                )
                self.gemini_available = True
                logger.info("AION Brain: Gemini API initialized successfully (SECONDARY).")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini API: {e}")
        else:
            logger.warning("No GEMINI_API_KEY found. Gemini will not be available.")

        # ── Initialize Ollama (Fallback) ────────────────────────
        try:
            import ollama as _ollama_module
            self._ollama = _ollama_module
            # Quick connectivity check — list local models
            self._ollama.list()
            self.ollama_available = True
            logger.info(f"AION Brain: Ollama initialized successfully (FALLBACK, model={self.ollama_model}).")
        except Exception as e:
            logger.warning(f"Ollama is not available: {e}. AION will only use cloud models.")
            self._ollama = None

        if not self.groq_available and not self.gemini_available and not self.ollama_available:
            logger.error("AION Brain: No AI brains (Groq, Gemini, Ollama) are available! Only local search will work.")

    # ════════════════════════════════════════════════════════════
    # Main entry point — called from gui_server.py
    # ════════════════════════════════════════════════════════════
    def process_command(self, text: str) -> str:
        text = text.strip()
        if not text:
            return "I didn't hear anything."

        # 1. First, check if it's a specific system command (File Search or WhatsApp)
        if self.file_manager.is_file_search_intent(text):
            logger.info("Command routed to FileSearchManager.")
            return self.file_manager.handle_command(text)

        # 2. Try Groq first (Primary Brain)
        if self.groq_available:
            result = self._try_groq(text)
            if result is not None:
                return result
            logger.warning("Groq failed. Falling back...")

        # 3. Try Gemini (Secondary Brain)
        if self.gemini_available:
            result = self._try_gemini(text)
            if result is not None:
                return result
            logger.warning("Gemini failed. Falling back...")

        # 4. Fallback to Ollama
        if self.ollama_available:
            result = self._try_ollama(text)
            if result is not None:
                return result

        # 5. Nothing available
        return "I am AION, but all my brains (Groq, Gemini, Ollama) are unavailable. I can only help you search for local files."

    # ════════════════════════════════════════════════════════════
    # Groq handler (Cloud, insane speed, tool calling support)
    # ════════════════════════════════════════════════════════════
    def _try_groq(self, text: str) -> Optional[str]:
        try:
            logger.info(f"Command routed to Groq ({self.groq_model}): {text}")

            if not self.groq_history:
                self.groq_history.append({
                    "role": "system",
                    "content": SYSTEM_PROMPT
                })

            self.groq_history.append({"role": "user", "content": text})

            # Send request to Groq
            response = self.groq_client.chat.completions.create(
                model=self.groq_model,
                messages=self.groq_history,
                tools=ollama_tool_definitions,
                tool_choice="auto"
            )

            assistant_message = response.choices[0].message
            max_iterations = 5
            iteration = 0
            tool_results_summary = []

            while assistant_message.tool_calls and iteration < max_iterations:
                iteration += 1

                # Add assistant message to history
                self.groq_history.append(assistant_message)

                for tool_call in assistant_message.tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)

                    logger.info(f"Groq requested tool: {func_name}({func_args})")

                    # Execute the tool
                    func = aion_tool_map.get(func_name)
                    if func:
                        try:
                            result = func(**func_args)
                            tool_results_summary.append(result)
                        except Exception as tool_err:
                            result = f"Tool execution error: {tool_err}"
                            logger.error(f"Tool {func_name} error: {tool_err}")
                    else:
                        result = f"Unknown tool: {func_name}"
                        logger.warning(f"Groq requested unknown tool: {func_name}")

                    logger.info(f"Tool result: {result}")

                    # Feed the tool result back
                    self.groq_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": func_name,
                        "content": result
                    })

                # Call Groq again with the tool results
                response = self.groq_client.chat.completions.create(
                    model=self.groq_model,
                    messages=self.groq_history,
                    tools=ollama_tool_definitions,
                    tool_choice="auto"
                )
                assistant_message = response.choices[0].message

            if tool_results_summary:
                final_text = " ".join(tool_results_summary)
            else:
                final_text = assistant_message.content or "Done! I've completed the task."

            # Save final response to history
            self.groq_history.append({"role": "assistant", "content": final_text})

            # Keep history manageable
            if len(self.groq_history) > 21:
                system_msg = self.groq_history[0]
                self.groq_history = [system_msg] + self.groq_history[-20:]

            return final_text

        except Exception as e:
            logger.error(f"Groq API error: {e}")
            return None

    # ════════════════════════════════════════════════════════════
    # Gemini handler (cloud, fast, tool-calling via automatic FC)
    # ════════════════════════════════════════════════════════════
    def _try_gemini(self, text: str) -> Optional[str]:
        try:
            logger.info(f"Command routed to Gemini AI: {text}")
            response = self.gemini_chat.send_message(text)
            return response.text
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Gemini API error: {e}")

            if "RECITATION" in error_msg:
                return "Sorry, the AI blocked my response because the generated code looked too much like copyrighted material (Recitation Filter). Please try asking for a different script!"

            # For rate-limit, quota, or network errors — return None to trigger fallback
            return None

    # ════════════════════════════════════════════════════════════
    # Ollama handler (local, unlimited, manual tool-calling loop)
    # ════════════════════════════════════════════════════════════
    def _try_ollama(self, text: str) -> Optional[str]:
        try:
            logger.info(f"Command routed to Ollama ({self.ollama_model}): {text}")

            # Add system prompt if this is the first message
            if not self.ollama_history:
                self.ollama_history.append({
                    "role": "system",
                    "content": SYSTEM_PROMPT
                })

            # Add the user's message
            self.ollama_history.append({"role": "user", "content": text})

            # Send to Ollama with tool definitions
            response = self._ollama.chat(
                model=self.ollama_model,
                messages=self.ollama_history,
                tools=ollama_tool_definitions
            )

            assistant_message = response.message

            # ── Tool-calling loop ───────────────────────────────
            # Ollama may request one or more tool calls. We execute
            # them and feed the results back until Ollama gives a
            # final text response (no more tool calls).
            max_iterations = 5  # Safety limit to prevent infinite loops
            iteration = 0
            tool_results_summary = []  # Track what tools did

            while assistant_message.tool_calls and iteration < max_iterations:
                iteration += 1

                # Add the assistant's tool-call message to history
                self.ollama_history.append(assistant_message.model_dump())

                # Execute each tool call
                for tool_call in assistant_message.tool_calls:
                    func_name = tool_call.function.name
                    func_args = tool_call.function.arguments

                    logger.info(f"Ollama requested tool: {func_name}({func_args})")

                    # Look up and execute the tool
                    func = aion_tool_map.get(func_name)
                    if func:
                        try:
                            result = func(**func_args)
                            tool_results_summary.append(result)
                        except Exception as tool_err:
                            result = f"Tool execution error: {tool_err}"
                            logger.error(f"Tool {func_name} error: {tool_err}")
                    else:
                        result = f"Unknown tool: {func_name}"
                        logger.warning(f"Ollama requested unknown tool: {func_name}")

                    logger.info(f"Tool result: {result}")

                    # Feed the tool result back to Ollama
                    self.ollama_history.append({
                        "role": "tool",
                        "content": result
                    })

                # Ask Ollama again with the tool results
                response = self._ollama.chat(
                    model=self.ollama_model,
                    messages=self.ollama_history,
                    tools=ollama_tool_definitions
                )
                assistant_message = response.message

            # ── Final text response ─────────────────────────────
            # If tools were executed, use a clean summary instead of
            # Ollama's verbose follow-up (which often dumps raw code).
            if tool_results_summary:
                final_text = " ".join(tool_results_summary)
            else:
                final_text = assistant_message.content or "Done! I've completed the task."

            # Save assistant's final response to history for context
            self.ollama_history.append({"role": "assistant", "content": final_text})

            # Keep history manageable (last 20 messages + system prompt)
            if len(self.ollama_history) > 21:
                system_msg = self.ollama_history[0]
                self.ollama_history = [system_msg] + self.ollama_history[-20:]

            return final_text

        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return f"Both my cloud brain (Gemini) and local brain (Ollama) encountered errors. Error: {e}"
