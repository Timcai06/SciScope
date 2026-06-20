CREATE TABLE IF NOT EXISTS papers (
    paper_uid TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    doi TEXT,
    title TEXT NOT NULL,
    abstract TEXT NOT NULL DEFAULT '',
    year INTEGER,
    field TEXT NOT NULL DEFAULT 'unknown',
    full_text TEXT NOT NULL DEFAULT '',
    query TEXT NOT NULL DEFAULT '',
    field_seed TEXT NOT NULL DEFAULT '',
    crawled_at TEXT NOT NULL DEFAULT '',
    is_recent_window BOOLEAN NOT NULL DEFAULT false,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    search_document TSVECTOR GENERATED ALWAYS AS (
        to_tsvector(
            'simple',
            coalesce(title, '') || ' ' ||
            coalesce(abstract, '') || ' ' ||
            coalesce(field, '') || ' ' ||
            coalesce(full_text, '')
        )
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS papers_source_source_id_idx ON papers (source, source_id);
CREATE INDEX IF NOT EXISTS papers_year_idx ON papers (year);
CREATE INDEX IF NOT EXISTS papers_source_idx ON papers (source);
CREATE INDEX IF NOT EXISTS papers_field_idx ON papers (field);
CREATE INDEX IF NOT EXISTS papers_search_document_idx ON papers USING GIN (search_document);

CREATE TABLE IF NOT EXISTS authors (
    author_uid TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS authors_normalized_name_idx ON authors (normalized_name);

CREATE TABLE IF NOT EXISTS paper_authors (
    paper_uid TEXT NOT NULL REFERENCES papers (paper_uid) ON DELETE CASCADE,
    author_uid TEXT NOT NULL REFERENCES authors (author_uid) ON DELETE CASCADE,
    author_position INTEGER NOT NULL,
    PRIMARY KEY (paper_uid, author_uid)
);

CREATE INDEX IF NOT EXISTS paper_authors_author_idx ON paper_authors (author_uid);

CREATE TABLE IF NOT EXISTS keywords (
    keyword_uid TEXT PRIMARY KEY,
    keyword TEXT NOT NULL,
    normalized_keyword TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS keywords_normalized_keyword_idx ON keywords (normalized_keyword);

CREATE TABLE IF NOT EXISTS paper_keywords (
    paper_uid TEXT NOT NULL REFERENCES papers (paper_uid) ON DELETE CASCADE,
    keyword_uid TEXT NOT NULL REFERENCES keywords (keyword_uid) ON DELETE CASCADE,
    PRIMARY KEY (paper_uid, keyword_uid)
);

CREATE INDEX IF NOT EXISTS paper_keywords_keyword_idx ON paper_keywords (keyword_uid);

CREATE TABLE IF NOT EXISTS paper_chunks (
    chunk_uid TEXT PRIMARY KEY,
    paper_uid TEXT NOT NULL REFERENCES papers (paper_uid) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_type TEXT NOT NULL,
    source_field TEXT NOT NULL,
    text TEXT NOT NULL,
    token_estimate INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    search_document TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(text, ''))
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS paper_chunks_paper_index_idx ON paper_chunks (paper_uid, chunk_index);
CREATE INDEX IF NOT EXISTS paper_chunks_type_idx ON paper_chunks (chunk_type);
CREATE INDEX IF NOT EXISTS paper_chunks_search_document_idx ON paper_chunks USING GIN (search_document);

CREATE TABLE IF NOT EXISTS coauthor_edges (
    author_uid_a TEXT NOT NULL REFERENCES authors (author_uid) ON DELETE CASCADE,
    author_uid_b TEXT NOT NULL REFERENCES authors (author_uid) ON DELETE CASCADE,
    weight INTEGER NOT NULL DEFAULT 1,
    first_year INTEGER,
    last_year INTEGER,
    PRIMARY KEY (author_uid_a, author_uid_b)
);

CREATE INDEX IF NOT EXISTS coauthor_edges_weight_idx ON coauthor_edges (weight DESC);
