import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List

# Load environment variables from .env file
load_dotenv()

# Gemini API key
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable not set.")

# The SDK handles the connection logic here.
client = genai.Client(api_key=api_key)

# create app instance
app = FastAPI()
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:3000"], # Allow your React app
#     allow_credentials=True,
#     allow_methods=["*"], # Allow all methods (POST, GET, etc)
#     allow_headers=["*"],
# )

# 1. Define the Message structure
class Message(BaseModel):
    role: str
    content: str

# 2. Update the Request Model
class ChatRequest(BaseModel):
    messages: List[Message] # Now accepts the whole history

# define path operation for health check endpoint
@app.get("/health_check")
async def health_check():
    """Health check endpoint to verify the service is running."""
    return {"status": "Hello, World!"}

# --- THE ENDPOINT ---
@app.post("/stream")
async def stream_chat(request: ChatRequest):
    
    # 1. Define the "Sales Engineer" Persona
    # We explicitly tell it to use its search tool on a specific domain.
    system_instruction = """
    You are a helpful, expert Neo4j Sales Engineer. 
    Your goal is to answer technical questions for customers clearly and concisely.

    GUIDELINES:
    1. CONTEXT FIRST: Base your answers strictly on the search results or provided context. Do not hallucinate features.
    2. CONCISENESS: Keep answers to 1-2 short paragraphs. Avoid long lectures.
    3. CODE: Do NOT provide code examples unless the user specifically asks for them, or if a 1-line snippet is necessary for clarity.
    4. LINKS: Provide citations as inline markdown links (e.g., "See the [Cypher Manual](url)..."). Do not add a "Sources" list at the end.  SOURCE ALL TECHNICAL CLAIMS.
    5. TONE: Be conversational but professional. (e.g., "You can use...")

    If the answer is simple and you are confident, state it directly without over-searching.
    """

    async def generate_chunks():
        try:
            # 2. Build the history string
            conversation_history = system_instruction + "\n\n"
            for msg in request.messages:
                conversation_history += f"{msg.role.upper()}: {msg.content}\n"
            conversation_history += "BOT:"

            # 3. Call Gemini with Search Enabled
            # We add the 'tools' configuration here.
            response_stream = await client.aio.models.generate_content_stream(
                model="gemini-2.5-flash",
                contents=conversation_history,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(
                        google_search=types.GoogleSearch() # <--- THE MAGIC SWITCH
                    )],
                    response_modalities=["TEXT"]
                )
            )
            
            async for chunk in response_stream:
                # Grounding chunks sometimes come back with metadata (sources), 
                # but 'chunk.text' contains the actual synthesized answer.
                if chunk.text:
                    yield chunk.text
                    
        except Exception as e:
            yield f"\nError: {str(e)}"

    return StreamingResponse(generate_chunks(), media_type="text/plain")

app.mount("/", StaticFiles(directory="static", html=True), name="static")