# Expose the Connection components
from .embedder import process_pending_nodes, embeddings_model

__all__ = [
    "process_pending_nodes",
    "embeddings_model"
]