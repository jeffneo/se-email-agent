import os
from dotenv import load_dotenv
import asyncio

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi import BackgroundTasks

from contextlib import asynccontextmanager
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from pydantic import BaseModel
from typing import List
from datetime import datetime

from database import init_driver, close_driver, query as query_neo4j
from graph import build_graph
from services.embedder import process_pending_nodes

# --- GLOBAL GRAPH INSTANCE ---
app_graph = None

# --- LIFESPAN MANAGER ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- PHASE 1: STARTUP ---
    # This code runs ONE TIME when you press 'Play' (start uvicorn).
    # It's where you open connections, load ML models, or read config files.
    await init_driver()
    print("🚀 App is ready to receive requests!")

    # Build the Graph once at startup.
    # (Since our config is static for now, this is efficient)
    global app_graph
    app_graph = build_graph()

    # --- PHASE 2: THE PAUSE BUTTON (YIELD) ---
    # The application "pauses" here and goes to work.
    # It stays in this state for days/weeks, serving user requests.
    yield 

    # --- PHASE 3: SHUTDOWN ---
    # This code runs ONE TIME when you press 'Ctrl+C' (stop uvicorn).
    # It ensures you close the database connection safely before the process dies.
    print("🛑 App is shutting down...")
    await close_driver()

# create app instance
app = FastAPI(lifespan=lifespan)
# CORS (Allow frontend to talk to backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Define the Message structure
class Message(BaseModel):
    id: str
    role: str
    content: str

# 2. Update the Request Model
class ChatRequest(BaseModel):
    messages: List[Message] # Now accepts the whole history
    threadId: str

# define path operation for health check endpoint
@app.get("/health_check")
async def health_check():
    """Health check endpoint to verify the service is running."""
    return {"status": "Hello, World!"}

# --- THE ENDPOINT ---
@app.post("/stream")
async def stream_chat(request: ChatRequest):
    """
    The main chat endpoint.
    It purely handles I/O. The Logic is all in the Graph.
    """
    print(f"Received request with {len(request.messages)} messages at {datetime.now().isoformat()}")
    
    # 1. Convert Frontend JSON -> LangChain Messages
    # CRITICAL CHANGE: We do NOT inject the System Prompt here anymore.
    # The 'agent_node' in graph/nodes.py handles that dynamically.
    history = []
    
    for msg in request.messages:
        if msg.role == "user":
            history.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            history.append(AIMessage(content=msg.content))
        # Security: Ignore 'system' messages from frontend to prevent prompt injection
            
    # 2. Generator function
    async def generate():
        if not app_graph:
            yield "Error: Graph not initialized."
            return
            
        # Stream events from the graph
        async for event in app_graph.astream_events(
            {"messages": history, "thread_id": request.threadId}, 
            version="v1"
        ):
            kind = event["event"]
            
            # "on_chat_model_stream" is when the LLM is writing text
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                content = chunk.content
                
                if content:
                    # Robust handling for string vs list content
                    if isinstance(content, str):
                        yield content
                    elif isinstance(content, list):
                         for block in content:
                            if isinstance(block, str):
                                yield block
                            elif isinstance(block, dict) and "text" in block:
                                yield block["text"]
            
        asyncio.create_task(process_pending_nodes())

    return StreamingResponse(generate(), media_type="text/plain")

@app.get("/api/test-db")
async def test_db():
    try:
        # Use our new helper function
        result = await query_neo4j("RETURN 'Hello from Aura!' AS message")
        record = result.records[0]
        return {"status": "success", "message": record["message"]}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- STATIC FILES ---
# Mount the frontend if it exists
frontend_path = os.path.join(os.path.dirname(__file__), "../frontend/dist")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")