import json
import hashlib
import logging
from datetime import datetime
from typing import List, Dict, Any

# LangChain Imports
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage, BaseMessage

# Local Imports
from db import get_driver, query as query_neo4j

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_message_id(thread_id: str, index: int, role: str, content: str) -> str:
    """
    Generates a deterministic hash.
    Ensures that if we save the same conversation twice, we don't create duplicate nodes.
    """
    # Take the first 50 chars to keep the hash stable even if tail content changes slightly
    safe_content = str(content)[:50] 
    raw_str = f"{thread_id}-{index}-{role}-{safe_content}"
    return hashlib.md5(raw_str.encode("utf-8")).hexdigest()

def clean_content(content: Any) -> str:
    """
    SANITIZER: Forces any input into a Neo4j-safe String.
    Handles:
    - Simple Strings
    - LangChain Lists (Stream chunks)
    - Google Metadata (Dictionaries with 'extras')
    """
    if content is None:
        return ""
        
    # 1. Simple String
    if isinstance(content, str):
        return content

    # 2. List (Stream Chunks or Tool Calls)
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict):
                # If it has a 'text' key, use it. Ignore 'extras', 'signature', etc.
                if "text" in item:
                    text_parts.append(str(item["text"]))
        # Join all text parts found
        return "".join(text_parts)

    # 3. Dict (Tool Call Payload)
    if isinstance(content, dict):
        # If it has text, return it. Otherwise, JSON dump it so we don't lose the data.
        return str(content.get("text", json.dumps(content)))

    # 4. Fallback
    return str(content)

def extract_sources(msg: ToolMessage) -> List[Dict[str, str]]:
    """
    Parses a ToolMessage to find URLs and Titles.
    Expects the content to be a JSON string or a List of Dicts (from Tavily).
    """
    try:
        content = msg.content
        data = []

        # Parse JSON if needed
        if isinstance(content, str):
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                return [] # Not JSON, probably just an error string
        elif isinstance(content, list):
            data = content
        
        # Normalize to list if it's a single dict
        if isinstance(data, dict):
            data = [data]

        valid_sources = []
        for item in data:
            if isinstance(item, dict) and "url" in item:
                valid_sources.append({
                    "url": item["url"],
                    "title": item.get("title", "No Title"),
                    "content": clean_content(item.get("content", ""))[:500] # Truncate for sanity
                })
        return valid_sources

    except Exception as e:
        logger.warning(f"Failed to extract sources from tool message: {e}")
        return []

async def persist_chat(user_id: str, thread_id: str, messages: List[BaseMessage]):
    driver = get_driver()
    if not driver:
        logger.warning("⚠️ No DB driver available. Skipping persistence.")
        return

    serialized_messages = []
    
    # We use a filtered index because we might skip empty messages (like ThinkingDots)
    current_index = 0

    for msg in messages:
        # 1. Determine Role
        role = "unknown"
        if isinstance(msg, HumanMessage): role = "user"
        elif isinstance(msg, AIMessage): role = "assistant"
        elif isinstance(msg, SystemMessage): role = "system"
        elif isinstance(msg, ToolMessage): role = "tool"
        
        # 2. Clean Content
        content_str = clean_content(msg.content)

        # 3. Skip Empty Messages (ThinkingDots)
        if not content_str or not content_str.strip():
            continue

        # 4. Generate ID
        msg_id = generate_message_id(thread_id, current_index, role, content_str)
        
        msg_data = {
            "id": msg_id,
            "index": current_index,
            "role": role,
            "content": content_str,
            "sources": []
        }

        # 5. Extract Sources (Only for Tools)
        if isinstance(msg, ToolMessage):
            msg_data["sources"] = extract_sources(msg)

        serialized_messages.append(msg_data)
        current_index += 1

    # --- THE CYPHER QUERY ---
    query = """
    MERGE (u:User {email: $user_id})
    MERGE (t:Thread {id: $thread_id})
    MERGE (u)-[:PARTICIPATED_IN]->(t)

    WITH t
    UNWIND $messages AS msg_data
    
    // Create Message
    MERGE (m:Message {id: msg_data.id})
    ON CREATE SET 
        m.role = msg_data.role,
        m.content = msg_data.content,
        m.index = msg_data.index,
        m.created_at = datetime()
    
    // Link to Thread
    MERGE (t)-[:HAS_MESSAGE]->(m)

    // Create Sources (if any)
    FOREACH (source IN msg_data.sources | 
        MERGE (s:Source {url: source.url})
        ON CREATE SET 
            s.title = source.title,
            s.text = source.content,
            s.crawled_at = datetime()
        MERGE (m)-[:RETRIEVED]->(s)
    )
    """
    
    # --- CHAIN LINKING QUERY (Separate for cleanliness) ---
    chain_query = """
    MATCH (t:Thread {id: $thread_id})-[:HAS_MESSAGE]->(m:Message)
    WITH m ORDER BY m.index ASC
    WITH collect(m) AS messages
    FOREACH (i IN range(0, size(messages)-2) |
        FOREACH (curr IN [messages[i]] |
            FOREACH (next IN [messages[i+1]] |
                MERGE (curr)-[:NEXT]->(next)
            )
        )
    )
    """

    try:
        # Execute Query using the query fn from db.py
        await query_neo4j(query, {
            "user_id": user_id, 
            "thread_id": thread_id, 
            "messages": serialized_messages
        })

        await query_neo4j(chain_query, {
            "thread_id": thread_id
        })

        logger.info(f"✅ Persisted {len(serialized_messages)} messages to Neo4j.")
        
    except Exception as e:
        logger.error(f"❌ Failed to persist chat: {e}")