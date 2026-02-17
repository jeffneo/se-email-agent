from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import tools_condition, ToolNode
from langgraph.graph.message import add_messages
from typing import TypedDict, Annotated, List, Optional
from langchain_core.messages import SystemMessage

# --- IMPORTS (Absolute from backend/ root) ---
from agent_config import technical_email_config
from database import query, save_chat_history, VECTOR_LOOKUP
from tools import search_web
from services import embeddings_model

# --- LOCAL IMPORTS (Sibling) ---
from .nodes import make_agent_node

# --- STATE DEFINITION ---
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    thread_id: str
    # hold retrieved context (useful for debugging or UI)
    context: Optional[str]
    # Store the IDs of the chunks we found
    context_ids: Optional[List[str]]

# --- CONTEXT RETRIEVAL ---
async def retrieve_context_node(state: AgentState):
    """
    1. Extract the user's latest query.
    2. Embed it using Gemini.
    3. Search Neo4j for semantically similar past messages.
    4. Inject context if found.
    """
    last_message = state["messages"][-1]
    user_query = last_message.content

    # 1. Generate Embedding
    # We use aembed_query (optimized for search queries) vs aembed_documents (for storage)
    query_vector = await embeddings_model.aembed_query(user_query)
    
    # 2. Run Vector Search
    # Note: Ensure your index name 'messageContent_vector_idx' exists in the DB.
    
    try:
        result = await query(VECTOR_LOOKUP, {
            "vector": query_vector
        })
        
        # 3. Process Results
        contents = []
        if result.records:
            # The query returns a `content` field which is a list of relevant past messages (could be empty)
            source_ids = [record["id"] for record in result.records if record["content"]]
            contents = [result["content"] for result in result.records if result["content"]]
        
        if contents:
            context_text = "\n---\n".join(contents)
            print(f"✅ Found {len(contents)} relevant past messages.")
            
            # 4. Inject Context
            context_msg = SystemMessage(
                content=f"INTERNAL KNOWLEDGE FOUND:\n{context_text}\n\n"
                        "INSTRUCTIONS: The above messages are from the user's past conversations. "
                        "Use them to answer the question if relevant. "
                        "If the answer is fully contained here, you do NOT need to search the web."
            )
            return {"messages": [context_msg], "context": context_text, "context_ids": source_ids}
            
    except Exception as e:
        print(f"⚠️ Vector search failed: {e}")
        
    # Default: No context found
    return {"context": None, "context_ids": []}

# --- GRAPH BUILDER ---
def build_graph():
    """
    Constructs the state graph using the Technical Email Answerer persona.
    """
    builder = StateGraph(AgentState)
    
    # 1. define Tools
    # (Future: You can swap this list based on the config too)
    tools = [search_web]
    tool_node = ToolNode(tools)
    
    # 2. Create the Agent Node using our Factory
    # This injects the persona and the date handling logic
    agent_node = make_agent_node(technical_email_config, tools)
    
    # 3. Define Nodes
    builder.add_node("context_check", retrieve_context_node)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)
    
    # 4. Define Memory Node
    async def memory_node(state: AgentState):
        # TODO: Pass user_id context properly
        await save_chat_history(
            user_id="user_default",
            thread_id=state["thread_id"],
            messages=state["messages"],
            context_ids=state.get("context_ids", [])
        )
        return {}
        
    builder.add_node("memory", memory_node)
    
    # 5. Define Edges
    # START -> Check Context -> Agent
    builder.add_edge(START, "context_check") 
    builder.add_edge("context_check", "agent")
    
    # Conditional Logic: Agent decides "Do I have enough info?"
    # If Context was found, Agent likely goes straight to __end__ (Memory)
    # If Context was null, Agent likely goes to "tools"
    builder.add_conditional_edges(
        "agent",
        tools_condition,
        path_map={
            "tools": "tools",     
            "__end__": "memory"   
        }
    )
    
    # Loop back: Tools -> Agent
    builder.add_edge("tools", "agent")
    
    # Finish: Memory -> END
    builder.add_edge("memory", END)

    return builder.compile()