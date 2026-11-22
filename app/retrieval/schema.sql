-- ==============================================================================
-- Verifiable Support Agent v2 — pgvector Database Schema
-- Defines PostgreSQL vector extension, resolutions table, and HNSW ANN index.
-- ==============================================================================

-- 1. Enable the pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Create the historical resolutions table
CREATE TABLE IF NOT EXISTS resolutions (
    id VARCHAR(64) PRIMARY KEY,
    brand_text VARCHAR(128) NOT NULL DEFAULT '@AppleSupport',
    issue_text TEXT NOT NULL,
    resolution_text TEXT NOT NULL,
    intent VARCHAR(64) NOT NULL,
    embedding vector(768) NOT NULL,
    source_hash VARCHAR(64) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Approximate Nearest Neighbor (ANN) Index using HNSW
-- Metric: vector_cosine_ops (Cosine Distance)
-- Parameters:
--   m = 16 (number of bidirectional links per graph node)
--   ef_construction = 64 (size of dynamic candidate list during graph construction)
CREATE INDEX IF NOT EXISTS resolutions_embedding_hnsw_idx
ON resolutions
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- 4. B-Tree Indexes for hybrid metadata filtering
CREATE INDEX IF NOT EXISTS resolutions_intent_idx ON resolutions(intent);
CREATE INDEX IF NOT EXISTS resolutions_source_hash_idx ON resolutions(source_hash);
