import os
import logging
from neo4j import AsyncGraphDatabase

from .schema import NEO4J_SCHEMA

# Set up logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Global variable to hold the driver
driver = None
NEO4J_DB = "neo4j" # Default database name

async def init_driver():
    """Initializes the Neo4j driver using env vars."""
    global driver, NEO4J_DB

    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")
    NEO4J_DB = os.getenv("NEO4J_DB", "neo4j")

    if not all([uri, user, password]):
        msg = "Missing Neo4j environment variables (NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD)"
        logger.error(msg)
        raise ValueError(msg)

    try:
        driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        
        # Verify Connectivity (includes DB check via Eager API)
        # We run a simple query to ensure the DB exists and we have access.
        await driver.execute_query(
            "RETURN 'Connection Verified' AS status", 
            database_=NEO4J_DB
        )

        logger.info(f"✅ Connected to Neo4j at {uri} (Database: {NEO4J_DB})")

        # --- ROBUST SCHEMA APPLICATION ---
        logger.info("⚙️  Applying schema...")
        
        # Split the raw string by semicolon
        # We filter out empty lines to avoid syntax errors
        statements = [
            stmt.strip() for stmt in NEO4J_SCHEMA.split(";") 
            if stmt.strip()
        ]

        # Run each statement individually
        # We use a managed session so we get retries for free
        async with driver.session(database=NEO4J_DB) as session:
            for statement in statements:
                try:
                    await session.run(statement)
                except Exception as e:
                    # Log but don't crash the entire app if one index fails (e.g. already exists)
                    logger.warning(f"   ⚠️ Schema warning: {e}")
        
        logger.info(f"✅ Schema applied to database: {NEO4J_DB}")

    except Exception as e:
        logger.error(f"❌ Failed to connect to Neo4j: {e}")
        if driver:
            await driver.close()
        raise e

async def close_driver():
    """Closes the driver connection gracefully."""
    global driver
    if driver:
        await driver.close()
        logger.info("🔒 Neo4j driver closed.")

def get_driver():
    """
    Returns the raw driver instance.
    Useful if you need full control or streaming.
    """
    return driver

async def query(cypher: str, params: dict = None, db: str = None, **kwargs):
    """
    The Recommended Way to run queries.
    Wraps 'execute_query' to provide:
    1. Automatic Session Management
    2. Automatic Retries (Transient Errors)
    3. Cleaner Syntax
    
    Args:
        cypher: The Cypher query string
        params: Dictionary of parameters
        db: (Optional) Override the default database. 
            If None, uses the global NEO4J_DB.
        **kwargs: Alternative parameter specification (keyword conflicts)
    
    Returns:
        EagerResult object (records, summary, keys)
    """
    if not driver:
        raise ConnectionError("Neo4j driver is not initialized.")
        
    return await driver.execute_query(
        cypher, 
        parameters_=params or {}, 
        database_=db or NEO4J_DB,
        **kwargs
    )

# --- ISOLATED TESTING ---
if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv

    # 1. Load Env (Only for this test run)
    load_dotenv()

    async def run_test():
        print("--- 🧪 Testing DB Connection ---")
        
        try:
            await init_driver()

            # Test the wrapper function
            result = await query("RETURN 'Hello from execute_query' AS msg")
            print(f"Query Result: {result.records[0]['msg']}")
            
            await close_driver()
            print("--- ✅ Test Complete ---")
        except Exception as e:
            print(f"--- ❌ Test Failed: {e} ---")

    asyncio.run(run_test())