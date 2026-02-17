VECTOR_DIM = 384  # Default dimension for Gemini embeddings

NEO4J_SCHEMA = """
// --- Constraints (Uniqueness) ---
CREATE CONSTRAINT userEmail_key IF NOT EXISTS 
FOR (u:User) REQUIRE u.email IS NODE KEY;

CREATE CONSTRAINT threadId_key IF NOT EXISTS 
FOR (t:Thread) REQUIRE t.id IS NODE KEY;

CREATE CONSTRAINT msgId_key IF NOT EXISTS 
FOR (m:Message) REQUIRE m.id IS NODE KEY;

CREATE CONSTRAINT sourceUrl_key IF NOT EXISTS 
FOR (s:Source) REQUIRE s.url IS NODE KEY;

CREATE CONSTRAINT chunkId_key IF NOT EXISTS 
FOR (c:Chunk) REQUIRE c.id IS NODE KEY;

// --- Indexes (Speed) ---
CREATE INDEX msgTimestamp_idx IF NOT EXISTS 
FOR (m:Message) ON (m.created_at);

CREATE INDEX sourceCrawled_idx IF NOT EXISTS 
FOR (s:Source) ON (s.crawled_at);

// --- Vector indexes (Semantic Search) ---
CREATE VECTOR INDEX messageContent_vector_idx IF NOT EXISTS
FOR (m:Message) ON (m.embedding)
OPTIONS {indexConfig: {
    `vector.similarity_function`: "cosine",
    `vector.dimensions`: 384 // Match your embedding size
}};

CREATE VECTOR INDEX chunkContent_vector_idx IF NOT EXISTS
FOR (c:Chunk) ON (c.embedding)
OPTIONS {indexConfig: {
    `vector.similarity_function`: "cosine",
    `vector.dimensions`: 384 // Match your embedding size
}};
"""