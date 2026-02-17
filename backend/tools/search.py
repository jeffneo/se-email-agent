import os
import logging
from typing import List, TypedDict, Optional
from langchain_core.tools import tool
from tavily import TavilyClient

# --- 1. DEFINE THE SHAPE ---
# We explicitly define what a "Source" looks like.
# This acts as a contract for your frontend and your memory module.
class SearchResult(TypedDict):
    title: str
    url: str
    content: str
    score: float

# Configure logging to keep the console clean but informative
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 2. THE TOOL ---
@tool
def search_web(query: str, max_results: int = 3) -> List[SearchResult]:
    """
    Searches the web for the given query and returns a list of verified results.
    Useful for finding current events, documentation, or facts not in the database.
    
    Args:
        query: The search query string.
        max_results: The maximum number of results to return. Defaults to 3.
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        logger.error("TAVILY_API_KEY missing in environment variables.")
        # Fail gracefully: Return an empty list or a system error message
        # Returning a list with an error dict is better than crashing
        return [{
            "title": "Configuration Error",
            "url": "about:blank",
            "content": "Error: TAVILY_API_KEY not found. Search is disabled.",
            "score": 0.0
        }]

    client = TavilyClient(api_key=api_key)
    
    # Clean the query to remove accidental double-quotes which can break search
    clean_query = query.strip('"').strip("'")
    
    logger.info(f"🔎 Searching web for: {clean_query}")
    
    try:
        # We enforce a "site:" filter to keep results relevant to Neo4j
        # You can remove this f-string if you want broad internet search later
        targeted_query = f"site:neo4j.com/docs OR site:neo4j.com/labs {clean_query}"

        response = client.search(
            query=targeted_query, 
            search_depth="advanced", 
            max_results=max_results,
            include_raw_content=False # We want the AI-summarized 'content', not HTML
        )
        
        # --- 3. NORMALIZE THE OUTPUT ---
        # Map the raw API response to our strict SearchResult schema
        results: List[SearchResult] = []
        
        for result in response.get("results", []):
            # Handle potential missing keys safely
            results.append({
                "title": result.get("title", "No Title"),
                "url": result.get("url", "about:blank"),
                "content": result.get("content", ""),
                "score": result.get("score", 0.0)
            })
        
        # Log success summary
        logger.info(f"✅ Found {len(results)} results for '{clean_query}'")
        
        return results

    except Exception as e:
        logger.error(f"❌ Search failed: {e}")
        # Return a "System Message" style result so the LLM knows it failed
        return [{
            "title": "Search Failed",
            "url": "about:blank",
            "content": f"The search tool encountered an error: {str(e)}",
            "score": 0.0
        }]

# --- 4. ISOLATED TESTING ---
if __name__ == "__main__":
    # Allows you to run 'python backend/tools/search.py' to verify behavior
    from dotenv import load_dotenv
    load_dotenv()
    
    print("--- 🧪 Testing Search Tool ---")
    test_results = search_web.invoke({"query": "Neo4j vector index configuration"})
    
    for r in test_results:
        print(r)
        print("\n\n\n")