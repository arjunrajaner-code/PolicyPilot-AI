
import chromadb
from sentence_transformers import SentenceTransformer

from chunk_text import chunk_document


# Load the embedding model once
embedding_model = SentenceTransformer(
    "sentence-transformers/all-MiniLM-L6-v2"
)


def retrieve_relevant_chunks(
    document_text: str,
    question: str,
    source: str = "company_policy",
    top_k: int = 3,
) -> list[dict]:
    """
    Temporarily chunk, embed, and search a document.
    No persistent ChromaDB data is created.
    """

    if not question.strip():
        raise ValueError("Question cannot be empty.")

    # 1. Split the document into temporary chunks
    chunks = chunk_document(document_text)

    if not chunks:
        return []

    # 2. Generate temporary embeddings
    embeddings = embedding_model.encode(
        chunks,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).tolist()

    # 3. Create an in-memory ChromaDB client
    client = chromadb.EphemeralClient()

    collection = None

    try:
        # 4. Create a temporary collection
        collection = client.create_collection(
            name="policy_" + str(id(chunks)),
            metadata={"hnsw:space": "cosine"},
        )

        # 5. Store chunks and vectors temporarily
        collection.add(
            ids=[f"chunk-{i}" for i in range(len(chunks))],
            documents=chunks,
            embeddings=embeddings,
            metadatas=[
                {"chunk_id": i, "source": source}
                for i in range(len(chunks))
            ],
        )

        # 6. Embed the user's question
        question_embedding = embedding_model.encode(
            question,
            normalize_embeddings=True,
        ).tolist()

        # 7. Retrieve the most relevant chunks
        results = collection.query(
            query_embeddings=[question_embedding],
            n_results=min(top_k, len(chunks)),
            include=["documents", "metadatas", "distances"],
        )

        return [
            {
                "text": text,
                "metadata": metadata,
                "distance": distance,
            }
            for text, metadata, distance in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ]

    finally:
        # 8. Delete temporary collection and release client
        if collection is not None:
            client.delete_collection(collection.name)

        del client
