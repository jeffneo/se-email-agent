# backend/services/embedder.py
import os
import logging
from typing import List
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Import database tools
from database import query, FETCH_UNEMBEDDED_MESSAGES, FETCH_UNPROCESSED_SOURCES, WRITE_VECTOR_BATCH, WRITE_CHUNKS, VECTOR_DIM

logger = logging.getLogger(__name__)

# Initialize Gemini Embeddings
embeddings_model = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-001", # or text-embedding-004
    google_api_key=os.getenv("GEMINI_API_KEY"),
    output_dimensionality=VECTOR_DIM
)

# Initialize Splitter (for Web Pages)
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    separators=["\n\n", "\n", ".", " ", ""]
)

BATCH_SIZE = 50

async def process_pending_nodes():
    """
    The Main Maintenance Job.
    1. Finds Messages without embeddings.
    2. Finds Sources that haven't been chunked.
    """
    logger.info("🧹 Starting Maintenance: Embeddings & Chunking...")
    
    # --- A. PROCESS MESSAGES ---
    # Find messages with content but NO embedding
    records = await query(FETCH_UNEMBEDDED_MESSAGES)

    if records.records:
        logger.info(f"embedding {len(records.records)} messages...")
        
        # Batch Embed
        texts = [r["content"] for r in records.records]
        vectors = await embeddings_model.aembed_documents(texts)
        
        # Write Back
        # We use UNWIND to do this in one DB call per batch
        # Assume multiple batches of size BATCH_SIZE
        updates = [{"id": r["id"], "vector": v} for r, v in zip(records.records, vectors)]
        for i in range(0, len(updates), BATCH_SIZE):
            batch = updates[i:i + BATCH_SIZE]
            await query(WRITE_VECTOR_BATCH("Message"), {"batch": batch})

    # --- B. PROCESS SOURCES (CHUNKING) ---
    # Find sources that have text but NO chunks connected
    source_records = await query(FETCH_UNPROCESSED_SOURCES)

    for record in source_records.records:
        await _chunk_and_store_source(record["url"], record["text"])
        
    logger.info("✨ Maintenance Complete.")

async def _chunk_and_store_source(url: str, text: str):
    """
    Splits text into chunks, embeds them, and saves to Neo4j.
    """
    logger.info(f"📄 Chunking Source: {url}")
    
    # 1. Split Text
    chunks = text_splitter.split_text(text)
    if not chunks:
        return

    # 2. Embed Chunks
    vectors = await embeddings_model.aembed_documents(chunks)
    
    # 3. Prepare Data for Cypher
    chunk_data = []
    for i, (chunk_text, vector) in enumerate(zip(chunks, vectors)):
        chunk_data.append({
            "index": i,
            "text": chunk_text,
            "vector": vector
        })

    # 4. Save to Graph (Linear Chain Pattern)
    await query(WRITE_CHUNKS, {"url": url, "chunks": [{"index": chunk["index"], "text": chunk["text"]} for chunk in chunk_data]})
    # 5. Save Embeddings (Separate Query to set vectors after nodes are created)
    for i in range(0, len(chunk_data), BATCH_SIZE):
        batch = [{"id": f"{url}_{chunk['index']}", "vector": chunk["vector"]} for chunk in chunk_data[i:i + BATCH_SIZE]]
        await query(WRITE_VECTOR_BATCH("Chunk"), {"batch": batch})
