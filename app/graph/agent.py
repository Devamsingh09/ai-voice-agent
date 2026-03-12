"""
LangGraph Voice Agent — optimised for low latency.
stream_sentences() yields complete sentences as they arrive from LLM,
so TTS can start on sentence 1 while sentence 2 is still generating.
"""
import re
import sqlite3
from pathlib import Path
from typing import Generator

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver
from typing_extensions import TypedDict, Annotated

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


SYSTEM_PROMPT = SystemMessage(content="""You are a fast, friendly AI voice assistant.
Keep responses SHORT — 1 to 3 sentences maximum.
No markdown, no bullet points, no special characters.
Keep your voice Humanize and tone according to context.
Speak naturally as your response will be converted to speech.""")


def _get_llm() -> ChatGroq:
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set in .env")
    return ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model=settings.GROQ_MODEL,
        temperature=0.7,
        max_tokens=200,   # keep responses short = faster TTS
        streaming=True,
    )


def llm_node(state: AgentState) -> AgentState:
    llm = _get_llm()
    messages = [SYSTEM_PROMPT] + state["messages"]
    response = llm.invoke(messages)
    return {"messages": [response]}


def _build_graph(checkpointer):
    graph = StateGraph(AgentState)
    graph.add_node("llm", llm_node)
    graph.set_entry_point("llm")
    graph.add_edge("llm", END)
    return graph.compile(checkpointer=checkpointer)


class VoiceAgent:
    def __init__(self):
        db_path = Path(settings.DB_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._checkpointer = SqliteSaver(self._conn)
        self._graph = _build_graph(self._checkpointer)
        logger.info(f"✅ VoiceAgent ready | model={settings.GROQ_MODEL}")

    def stream_response(self, user_text: str, thread_id: str) -> Generator[str, None, None]:
        """Yield raw token chunks."""
        config = {"configurable": {"thread_id": thread_id}}
        try:
            for chunk, _ in self._graph.stream(
                {"messages": [HumanMessage(content=user_text)]},
                config=config,
                stream_mode="messages",
            ):
                if hasattr(chunk, "content") and chunk.content:
                    yield chunk.content
        except Exception as e:
            logger.error(f"LLM error: {e}")
            yield f"Sorry, I had an error: {e}"

    def stream_sentences(self, user_text: str, thread_id: str) -> Generator[str, None, None]:
        """
        Yield complete sentences as they arrive.
        This lets TTS start on sentence 1 while LLM is still generating sentence 2.
        """
        buffer = ""
        sentence_end = re.compile(r'(?<=[.!?])\s+')

        for token in self.stream_response(user_text, thread_id):
            buffer += token
            parts = sentence_end.split(buffer)
            # All parts except last are complete sentences
            for sentence in parts[:-1]:
                sentence = sentence.strip()
                if sentence:
                    yield sentence
            buffer = parts[-1]

        # Yield any remaining text
        if buffer.strip():
            yield buffer.strip()

    def get_history(self, thread_id: str) -> list[dict]:
        config = {"configurable": {"thread_id": thread_id}}
        try:
            state = self._graph.get_state(config)
            if not state or not state.values:
                return []
            history = []
            for msg in state.values.get("messages", []):
                if isinstance(msg, HumanMessage):
                    history.append({"role": "user", "content": msg.content})
                elif isinstance(msg, AIMessage):
                    history.append({"role": "assistant", "content": msg.content})
            return history
        except Exception as e:
            logger.error(f"History error: {e}")
            return []

    def clear_history(self, thread_id: str) -> bool:
        try:
            self._conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
            self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"Clear error: {e}")
            return False

    def list_sessions(self) -> list[str]:
        try:
            cursor = self._conn.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id")
            return [row[0] for row in cursor.fetchall()]
        except Exception:
            return []


_agent: VoiceAgent | None = None

def get_agent() -> VoiceAgent:
    global _agent
    if _agent is None:
        _agent = VoiceAgent()
    return _agent