import hashlib
import json
from pprint import pprint
import logging
from typing import List, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage

# Import from sibling files
from .connection import query as query_neo4j
from .queries import MERGE_CONVERSATION_TURN, LINK_SOURCES_FROM_VECTOR_LOOKUP

logger = logging.getLogger(__name__)

# --- UTILS (Private) ---
def _generate_id(thread_id: str, index: int, role: str, content: str) -> str:
    safe_content = str(content)[:50]
    raw = f"{thread_id}-{index}-{role}-{safe_content}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

def _clean_content(content: Any) -> str:
    """Sanitizes complex LLM outputs into a clean string."""
    if not content: return ""
    if isinstance(content, str): return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str): parts.append(item)
            elif isinstance(item, dict) and "text" in item: parts.append(str(item["text"]))
        return "".join(parts)
    if isinstance(content, dict): return str(content.get("text", json.dumps(content)))
    return str(content)

def _extract_sources(msg: ToolMessage) -> List[Dict]:
    """Parses tool outputs for source URLs."""
    try:
        data = msg.content
        if isinstance(data, str): 
            try: data = json.loads(data)
            except: return []
        
        if isinstance(data, dict): data = [data]
        if not isinstance(data, list): return []

        return [{
            "url": item.get("url"),
            "title": item.get("title", "No Title"),
            "content": _clean_content(item.get("content", ""))
        } for item in data if isinstance(item, dict) and "url" in item]
    except Exception:
        return []

# --- PUBLIC API ---
async def save_chat_history(
    user_id: str,
    thread_id: str,
    messages: List[BaseMessage],
    context_ids: List[str] = None
):
    """
    Main entry point to persist a conversation turn.
    """
    serialized_msgs = []
    current_index = 0

    for msg in messages:
        # 1. Map Role
        role = "unknown"
        if isinstance(msg, HumanMessage): role = "user"
        elif isinstance(msg, AIMessage): role = "assistant"
        elif isinstance(msg, ToolMessage): role = "tool"
        elif isinstance(msg, SystemMessage): continue # Skip system messages
        
        # 2. Clean Data
        content = _clean_content(msg.content)
        if not content.strip(): continue

        # 3. Build Object
        msg_data = {
            # "id": _generate_id(thread_id, current_index, role, content),
            "id": msg.id,
            "index": current_index,
            "role": role,
            "content": content if role in ["user", "assistant"] else None, # Only store content for user and assistant
            "sources": _extract_sources(msg) if role == "tool" else None
        }
        serialized_msgs.append(msg_data)
        current_index += 1

    # 4. Execute Queries
    try:
        # Create Nodes
        await query_neo4j(MERGE_CONVERSATION_TURN, {
            "user_id": user_id,
            "thread_id": thread_id,
            "messages": serialized_msgs
        })

        logger.info(f"✅ Saved {len(serialized_msgs)} messages to thread {thread_id}")

        # We assume the LAST AI message in the batch is the one that used the context.
        if context_ids:
            # Find the last assistant message in this batch to link
            last_ai_msg = next((m for m in reversed(serialized_msgs) if m["role"] == "assistant"), None)
            
            if last_ai_msg:
                await query_neo4j(LINK_SOURCES_FROM_VECTOR_LOOKUP, {
                    "msg_id": last_ai_msg["id"],
                    "source_ids": context_ids
                })
                logger.info(f"🔗 Linked {len(context_ids)} chunks to message {last_ai_msg['id']}")
    except Exception as e:
        logger.error(f"❌ DB Save Failed: {e}")