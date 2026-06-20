CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_uid TEXT PRIMARY KEY REFERENCES paper_chunks (chunk_uid) ON DELETE CASCADE,
    embedding_model TEXT NOT NULL,
    embedding vector(768) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chunk_embeddings_vector_idx
    ON chunk_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
