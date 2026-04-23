"""
Pinecone provider — placeholder for future RAG implementation.
"""


class PineconeProvider:
    """Stub for Pinecone vector search integration."""

    def __init__(self, api_key: str, index_name: str) -> None:
        # TODO: Initialize Pinecone client
        self.api_key = api_key
        self.index_name = index_name

    async def upsert_embeddings(self, vectors: list[dict]) -> None:
        # TODO: Upsert document embeddings into Pinecone index
        raise NotImplementedError("Pinecone upsert not implemented yet")

    async def query(self, embedding: list[float], top_k: int = 5) -> list[dict]:
        # TODO: Query Pinecone for similar documents
        raise NotImplementedError("Pinecone query not implemented yet")

    async def delete(self, ids: list[str]) -> None:
        # TODO: Delete vectors by ID
        raise NotImplementedError("Pinecone delete not implemented yet")
