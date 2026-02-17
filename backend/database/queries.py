# Creates the User, Thread, Message, and Source nodes in one atomic transaction
# Links messages sequentially with :NEXT relationships for easy traversal
# Links tool calls to their triggering messages and sources for full context
MERGE_CONVERSATION_TURN = """
    CYPHER 25

    MERGE (u:User {email: $user_id})
    MERGE (t:Thread {id: $thread_id})
    MERGE (u)-[:PARTICIPATED_IN]->(t)

    OPTIONAL MATCH (t)-[:FIRST]->(existingFirst)
    CALL (*) {
        WHEN existingFirst IS null THEN
            // No messages exist, create the first one
            MERGE (first:Message {id: $messages[0].id})
            ON CREATE SET 
                first.role = $messages[0].role,
                first.content = $messages[0].content,
                first.index = $messages[0].index,
                first.created_at = datetime()
            MERGE (t)-[:FIRST]->(first)
    }

    WITH t
    UNWIND [i IN range(0, size($messages) - 2) | [$messages[i], $messages[i + 1]]] AS pair
        WITH pair[0] AS msg_0, pair[1] AS msg_1, t

        CALL (*) {
            WHEN msg_1.role = "tool" THEN
                MERGE (m:ToolCall {id: msg_1.id})
                ON CREATE SET 
                    m.role = msg_1.role,
                    m.content = msg_1.content,
                    m.index = msg_1.index,
                    m.created_at = datetime()
                
                WITH m, msg_1

                // Create Sources
                FOREACH (source IN msg_1.sources | 
                    MERGE (s:Source {url: source.url})
                    ON CREATE SET 
                        s.title = source.title,
                        s.text = source.content,
                        s.crawled_at = datetime()
                    MERGE (m)-[:RETRIEVED]->(s)
                )
            ELSE
                MERGE (m:Message {id: msg_1.id})
                ON CREATE SET 
                    m.role = msg_1.role,
                    m.content = msg_1.content,
                    m.index = msg_1.index,
                    m.created_at = datetime()

                WITH m, msg_0, t

                OPTIONAL MATCH (tc:ToolCall {id: msg_0.id})
                CALL (*) {
                    WHEN tc IS NOT null THEN
                        MERGE (m)-[:TRIGGERED]->(tc)

                        WITH m, tc
                        OPTIONAL MATCH srcPath = (tc)-[:RETRIEVED]->(src:Source)
                        CALL (*) {
                            WHEN srcPath IS NOT null THEN
                                MERGE (m)-[:SOURCED]->(src)
                        }
                }

                WITH m, t
                
                MATCH threadPath = (t)-[:FIRST]->()-[:NEXT]->*(prev)
                WITH threadPath, length(threadPath) AS pathLength, m
                ORDER BY pathLength DESC LIMIT 1
                WITH m, last(nodes(threadPath)) AS prev
                MERGE (prev)-[:NEXT]->(m)
        }
"""

FETCH_UNEMBEDDED_MESSAGES = """
    MATCH (m:Message)
    WHERE m.embedding IS null AND m.content IS NOT null
    RETURN m.id AS id, m.content AS content
"""

FETCH_UNPROCESSED_SOURCES = """
    MATCH (s:Source)
    WHERE s.text IS NOT NULL AND NOT (s)-[:FIRST]->()
    RETURN s.url AS url, s.text AS text
"""

WRITE_CHUNKS = """
    MATCH (s:Source {url: $url})
    //SET s.text = null // Clear text to save space after chunking
    MERGE (c0:Chunk {id: s.url + "_0"})
    ON CREATE SET
        c0.content = head($chunks).text,
        c0.index = 0
    MERGE (s)-[:FIRST]->(c0)
    WITH s
    UNWIND [i IN range(0, size($chunks) - 2) | [$chunks[i], $chunks[i + 1]]] AS pair
    MATCH (prev:Chunk {id: s.url + "_" + toString(pair[0].index)})
    MERGE (c:Chunk {id: s.url + "_" + toString(pair[1].index)})
    ON CREATE SET
        c.content = pair[1].text,
        c.index = pair[1].index
    MERGE (prev)-[:NEXT]->(c)
"""

WRITE_VECTOR_BATCH = lambda label: f"""
    UNWIND $batch AS row
    MATCH (n:{label} {{id: row.id}})
    SET n.embedded_at = datetime()
    WITH n, row
    CALL db.create.setNodeVectorProperty(n, "embedding", row.vector)
"""

EP = 0.1

VECTOR_LOOKUP = f"""
    CALL db.index.vector.queryNodes("messageContent_vector_idx", 3, $vector)
    YIELD node, score
    WITH node, score
    WHERE score > {1.0 - EP}
    OPTIONAL MATCH (m)-[:NEXT]->{{0,1}}()-[:SOURCED]->(:Source|Chunk)-[:FIRST]->*(n WHERE n.content IS NOT null)
    RETURN DISTINCT n.id AS id, node.content AS content
    UNION DISTINCT
    CALL db.index.vector.queryNodes("chunkContent_vector_idx", 3, $vector)
    YIELD node, score
    WITH node, score
    WHERE score > {1.0 - EP}
    RETURN DISTINCT node.id AS id, node.content AS content
"""

# New syntax - generating an error for some reason
# VECTOR_LOOKUP = f"""
#     CYPHER 25

#     SEARCH node IN (
#         VECTOR INDEX messageContent_vector_idx
#         FOR $vector
#         LIMIT 3
#     ) SCORE AS score
#     WITH node, score
#     WHERE score > {1.0 - EP}
#     OPTIONAL MATCH (m)-[:NEXT]->{0,1}()-[:SOURCED]->(:Source|Chunk)-[:FIRST]->*(n WHERE n.content IS NOT null)
#     RETURN DISTINCT n.content AS content

#     UNION DISTINCT
    
#     SEARCH node IN (
#         VECTOR INDEX chunkContent_vector_idx
#         FOR $vector
#         LIMIT 3
#     ) SCORE AS score
#     WITH node.content AS content, score
#     WHERE score > {1.0 - EP}
#     RETURN content
# """

LINK_SOURCES_FROM_VECTOR_LOOKUP = """
    MATCH (m:Message {id: $msg_id})
    UNWIND $source_ids AS sid

    // Match loosely (could be a Chunk or a past Message)
    MATCH (src:Chunk|Message {id: sid}) 

    MERGE (m)-[:SOURCED]->(src)
"""