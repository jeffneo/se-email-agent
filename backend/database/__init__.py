# Expose the Connection components
from .connection import init_driver, close_driver, get_driver, query

# Expose the Repository components (The "Memory")
from .repository import save_chat_history

# Expose the Queries (Optional, but good for debugging)
from .queries import MERGE_CONVERSATION_TURN, FETCH_UNEMBEDDED_MESSAGES, FETCH_UNPROCESSED_SOURCES, WRITE_VECTOR_BATCH, VECTOR_LOOKUP, WRITE_CHUNKS, LINK_SOURCES_FROM_VECTOR_LOOKUP
from .schema import VECTOR_DIM

__all__ = [
    "init_driver",
    "close_driver",
    "get_driver",
    "query",
    "save_chat_history",
    "MERGE_CONVERSATION_TURN",
    "FETCH_UNEMBEDDED_MESSAGES",
    "FETCH_UNPROCESSED_SOURCES",
    "WRITE_VECTOR_BATCH",
    "WRITE_CHUNKS",
    "VECTOR_LOOKUP",
    "LINK_SOURCES_FROM_VECTOR_LOOKUP",
    "VECTOR_DIM"
]