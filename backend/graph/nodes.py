import os
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import ToolNode

# Relative import because this is a sibling file to workflow.py
# But 'agent_config' is at the root of backend, so we use absolute
from agent_config import AgentConfig

def make_agent_node(config: AgentConfig, tools: list):
    """
    Factory: Creates a runnable node function for a specific agent config.
    """
    # 1. Initialize the Model
    if not os.getenv("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY not found.")

    llm = ChatGoogleGenerativeAI(
        model=config.model_name,
        api_key=os.getenv("GEMINI_API_KEY"),
        temperature=config.temperature,
        streaming=True
    )
    
    # 2. Bind Tools
    llm_with_tools = llm.bind_tools(tools)
    
    # 3. Create the Node Function
    async def agent_node(state):
        messages = state["messages"]
        
        # --- DYNAMIC PROMPT INJECTION ---
        # Calculate date right now, when the node runs
        current_date = datetime.now().strftime("%B %d, %Y")
        
        # Format the template
        system_text = config.system_template.format(
            current_date=current_date
        )
        
        # Check if System Message exists. If not, prepend it.
        # If it does exist, we could optionally update it, but usually the first one wins.
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_text)] + messages
        
        # Invoke Model
        response = await llm_with_tools.ainvoke(messages)
        
        # Return new message (LangGraph appends it automatically)
        return {"messages": [response]}
        
    return agent_node