#!/usr/bin/env python3
"""Initialize the bibliographic_data.db SQLite database with full schema."""

import argparse
import sqlite3
import sys

SCHEMA_SQL = """\
-- ============================================================
-- Lookup/reference tables
-- ============================================================

CREATE TABLE IF NOT EXISTS assignee_role_code (
    code TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kind_code (
    code TEXT NOT NULL,
    dataset TEXT NOT NULL,  -- 'publication' or 'grant'
    description TEXT NOT NULL,
    PRIMARY KEY (code, dataset)
);

-- ============================================================
-- Processing metadata
-- ============================================================

CREATE TABLE IF NOT EXISTS processed_file (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL UNIQUE,
    dataset TEXT NOT NULL,  -- 'publication' or 'grant'
    file_date TEXT NOT NULL,
    week_number INTEGER,
    record_count INTEGER NOT NULL,
    processed_at TEXT NOT NULL,
    sha256 TEXT
);

CREATE TABLE IF NOT EXISTS processing_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,  -- 'INFO','WARNING','ERROR'
    dataset TEXT,         -- 'publication' or 'grant'
    message TEXT NOT NULL,
    detail TEXT
);

-- ============================================================
-- Entity tables (shared between publications and grants)
-- ============================================================

CREATE TABLE IF NOT EXISTS person (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    last_name TEXT,
    first_name TEXT,
    suffix TEXT,
    orgname TEXT,
    city TEXT,
    state TEXT,
    country TEXT,
    entity_hash TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS assignee (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    last_name TEXT,
    first_name TEXT,
    orgname TEXT,
    city TEXT,
    state TEXT,
    country TEXT,
    entity_hash TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS examiner (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    last_name TEXT,
    first_name TEXT,
    department TEXT,
    examiner_type TEXT NOT NULL DEFAULT 'primary',  -- 'primary' or 'assistant'
    entity_hash TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS attorney_agent_firm (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    last_name TEXT,
    first_name TEXT,
    orgname TEXT,
    city TEXT,
    state TEXT,
    country TEXT,
    rep_type TEXT,  -- 'attorney'
    entity_hash TEXT NOT NULL UNIQUE
);

-- ============================================================
-- Main tables
-- ============================================================

CREATE TABLE IF NOT EXISTS publication (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_reference TEXT,
    date_produced TEXT,
    date_published TEXT NOT NULL,
    dtd_version TEXT,
    country TEXT NOT NULL,
    doc_number TEXT NOT NULL,
    kind TEXT NOT NULL,
    pub_date TEXT NOT NULL,
    appl_type TEXT NOT NULL,
    appl_country TEXT,
    appl_doc_number TEXT,
    appl_date TEXT,
    series_code TEXT,
    invention_title TEXT,
    abstract_text TEXT,
    abstract_embedding BLOB,
    UNIQUE(country, doc_number, kind, pub_date)
);

CREATE TABLE IF NOT EXISTS grant (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_reference TEXT,
    date_produced TEXT,
    date_published TEXT NOT NULL,
    dtd_version TEXT,
    country TEXT NOT NULL,
    doc_number TEXT NOT NULL,
    kind TEXT NOT NULL,
    pub_date TEXT NOT NULL,
    appl_type TEXT NOT NULL,
    appl_country TEXT,
    appl_doc_number TEXT,
    appl_date TEXT,
    series_code TEXT,
    invention_title TEXT,
    number_of_claims INTEGER,
    exemplary_claim INTEGER,
    number_of_drawing_sheets INTEGER,
    number_of_figures INTEGER,
    abstract_text TEXT,
    abstract_embedding BLOB,
    UNIQUE(country, doc_number, kind, pub_date)
);

-- ============================================================
-- Junction tables — Publications
-- ============================================================

CREATE TABLE IF NOT EXISTS publication_inventor (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publication_id INTEGER NOT NULL REFERENCES publication(id),
    person_id INTEGER NOT NULL REFERENCES person(id),
    sequence INTEGER,
    designation TEXT,
    UNIQUE(publication_id, person_id)
);

CREATE TABLE IF NOT EXISTS publication_applicant (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publication_id INTEGER NOT NULL REFERENCES publication(id),
    person_id INTEGER NOT NULL REFERENCES person(id),
    sequence INTEGER,
    app_type TEXT,
    authority_category TEXT,
    designation TEXT,
    residence_country TEXT,
    UNIQUE(publication_id, person_id)
);

CREATE TABLE IF NOT EXISTS publication_assignee (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publication_id INTEGER NOT NULL REFERENCES publication(id),
    assignee_id INTEGER NOT NULL REFERENCES assignee(id),
    role TEXT,
    sequence INTEGER,
    UNIQUE(publication_id, assignee_id)
);

-- ============================================================
-- Junction tables — Grants
-- ============================================================

CREATE TABLE IF NOT EXISTS grant_inventor (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grant_id INTEGER NOT NULL REFERENCES grant(id),
    person_id INTEGER NOT NULL REFERENCES person(id),
    sequence INTEGER,
    designation TEXT,
    UNIQUE(grant_id, person_id)
);

CREATE TABLE IF NOT EXISTS grant_applicant (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grant_id INTEGER NOT NULL REFERENCES grant(id),
    person_id INTEGER NOT NULL REFERENCES person(id),
    sequence INTEGER,
    app_type TEXT,
    authority_category TEXT,
    designation TEXT,
    residence_country TEXT,
    UNIQUE(grant_id, person_id)
);

CREATE TABLE IF NOT EXISTS grant_assignee (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grant_id INTEGER NOT NULL REFERENCES grant(id),
    assignee_id INTEGER NOT NULL REFERENCES assignee(id),
    role TEXT,
    sequence INTEGER,
    UNIQUE(grant_id, assignee_id)
);

CREATE TABLE IF NOT EXISTS grant_examiner (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grant_id INTEGER NOT NULL REFERENCES grant(id),
    examiner_id INTEGER NOT NULL REFERENCES examiner(id),
    examiner_type TEXT NOT NULL,  -- 'primary' or 'assistant'
    UNIQUE(grant_id, examiner_id, examiner_type)
);

CREATE TABLE IF NOT EXISTS grant_attorney_agent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grant_id INTEGER NOT NULL REFERENCES grant(id),
    attorney_agent_id INTEGER NOT NULL REFERENCES attorney_agent_firm(id),
    sequence INTEGER,
    UNIQUE(grant_id, attorney_agent_id)
);

-- ============================================================
-- Classification tables
-- ============================================================

CREATE TABLE IF NOT EXISTS classification_ipcr (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,  -- 'publication' or 'grant'
    source_id INTEGER NOT NULL,
    ipc_version_date TEXT,
    classification_level TEXT,
    section TEXT,
    ipc_class TEXT,
    subclass TEXT,
    main_group TEXT,
    subgroup TEXT,
    symbol_position TEXT,
    classification_value TEXT,
    action_date TEXT,
    generating_office_country TEXT,
    classification_status TEXT,
    classification_data_source TEXT
);

CREATE TABLE IF NOT EXISTS classification_cpc (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    cpc_version_date TEXT,
    section TEXT,
    cpc_class TEXT,
    subclass TEXT,
    main_group TEXT,
    subgroup TEXT,
    symbol_position TEXT,
    classification_value TEXT,
    action_date TEXT,
    generating_office_country TEXT,
    classification_status TEXT,
    classification_data_source TEXT,
    scheme_origination_code TEXT,
    is_main BOOLEAN DEFAULT 0
);

CREATE TABLE IF NOT EXISTS classification_national (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    country TEXT,
    main_classification TEXT,
    additional_info TEXT
);

CREATE TABLE IF NOT EXISTS classification_locarno (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grant_id INTEGER NOT NULL REFERENCES grant(id),
    edition TEXT,
    main_classification TEXT
);

-- ============================================================
-- Priority claims
-- ============================================================

CREATE TABLE IF NOT EXISTS priority_claim (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    sequence INTEGER,
    kind TEXT,
    country TEXT,
    doc_number TEXT,
    date TEXT
);

-- ============================================================
-- PCT data
-- ============================================================

CREATE TABLE IF NOT EXISTS pct_filing_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    country TEXT,
    doc_number TEXT,
    date TEXT,
    us_371c12_date TEXT
);

CREATE TABLE IF NOT EXISTS pct_publishing_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    country TEXT,
    doc_number TEXT,
    kind TEXT,
    date TEXT
);

-- ============================================================
-- Related documents
-- ============================================================

CREATE TABLE IF NOT EXISTS related_document (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL,
    parent_country TEXT,
    parent_doc_number TEXT,
    parent_date TEXT,
    parent_status TEXT,
    parent_grant_doc_number TEXT,
    parent_grant_date TEXT,
    child_country TEXT,
    child_doc_number TEXT
);

-- ============================================================
-- References cited (grants only)
-- ============================================================

CREATE TABLE IF NOT EXISTS reference_cited (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grant_id INTEGER NOT NULL REFERENCES grant(id),
    citation_num TEXT,
    citation_type TEXT NOT NULL,  -- 'patent' or 'npl'
    pat_country TEXT,
    pat_doc_number TEXT,
    pat_kind TEXT,
    pat_name TEXT,
    pat_date TEXT,
    npl_text TEXT,
    category TEXT,
    classification_cpc_text TEXT
);

-- ============================================================
-- Botanic (plant patents)
-- ============================================================

CREATE TABLE IF NOT EXISTS botanic (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    latin_name TEXT,
    variety TEXT
);

-- ============================================================
-- Grant term (grants only)
-- ============================================================

CREATE TABLE IF NOT EXISTS grant_term (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grant_id INTEGER NOT NULL REFERENCES grant(id),
    length_of_grant INTEGER,
    term_disclaimer TEXT
);

-- ============================================================
-- Field of classification search (grants only)
-- ============================================================

CREATE TABLE IF NOT EXISTS field_of_classification_search (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grant_id INTEGER NOT NULL REFERENCES grant(id),
    search_country TEXT,
    search_main_classification TEXT,
    search_additional_info TEXT,
    search_cpc_text TEXT
);
"""

INDEXES_SQL = """\
-- Publication indexes
CREATE INDEX IF NOT EXISTS idx_publication_doc_number ON publication(country, doc_number, kind);
CREATE INDEX IF NOT EXISTS idx_publication_pub_date ON publication(pub_date);
CREATE INDEX IF NOT EXISTS idx_publication_appl_doc_number ON publication(appl_doc_number);

-- Grant indexes
CREATE INDEX IF NOT EXISTS idx_grant_doc_number ON grant(country, doc_number, kind);
CREATE INDEX IF NOT EXISTS idx_grant_pub_date ON grant(pub_date);
CREATE INDEX IF NOT EXISTS idx_grant_appl_doc_number ON grant(appl_doc_number);

-- Entity table indexes
CREATE INDEX IF NOT EXISTS idx_person_hash ON person(entity_hash);
CREATE INDEX IF NOT EXISTS idx_assignee_hash ON assignee(entity_hash);
CREATE INDEX IF NOT EXISTS idx_examiner_hash ON examiner(entity_hash);
CREATE INDEX IF NOT EXISTS idx_attorney_agent_hash ON attorney_agent_firm(entity_hash);

-- Publication junction indexes
CREATE INDEX IF NOT EXISTS idx_pub_inventor_pub ON publication_inventor(publication_id);
CREATE INDEX IF NOT EXISTS idx_pub_inventor_person ON publication_inventor(person_id);
CREATE INDEX IF NOT EXISTS idx_pub_applicant_pub ON publication_applicant(publication_id);
CREATE INDEX IF NOT EXISTS idx_pub_applicant_person ON publication_applicant(person_id);
CREATE INDEX IF NOT EXISTS idx_pub_assignee_pub ON publication_assignee(publication_id);
CREATE INDEX IF NOT EXISTS idx_pub_assignee_assignee ON publication_assignee(assignee_id);

-- Grant junction indexes
CREATE INDEX IF NOT EXISTS idx_grant_inventor_grant ON grant_inventor(grant_id);
CREATE INDEX IF NOT EXISTS idx_grant_inventor_person ON grant_inventor(person_id);
CREATE INDEX IF NOT EXISTS idx_grant_applicant_grant ON grant_applicant(grant_id);
CREATE INDEX IF NOT EXISTS idx_grant_applicant_person ON grant_applicant(person_id);
CREATE INDEX IF NOT EXISTS idx_grant_assignee_grant ON grant_assignee(grant_id);
CREATE INDEX IF NOT EXISTS idx_grant_assignee_assignee ON grant_assignee(assignee_id);
CREATE INDEX IF NOT EXISTS idx_grant_examiner_grant ON grant_examiner(grant_id);
CREATE INDEX IF NOT EXISTS idx_grant_examiner_examiner ON grant_examiner(examiner_id);
CREATE INDEX IF NOT EXISTS idx_grant_attorney_grant ON grant_attorney_agent(grant_id);
CREATE INDEX IF NOT EXISTS idx_grant_attorney_attorney ON grant_attorney_agent(attorney_agent_id);

-- Classification indexes
CREATE INDEX IF NOT EXISTS idx_class_ipcr_source ON classification_ipcr(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_class_cpc_source ON classification_cpc(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_class_national_source ON classification_national(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_class_locarno_grant ON classification_locarno(grant_id);

-- Other table indexes
CREATE INDEX IF NOT EXISTS idx_priority_claim_source ON priority_claim(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_pct_filing_source ON pct_filing_data(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_pct_publishing_source ON pct_publishing_data(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_related_doc_source ON related_document(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_reference_cited_grant ON reference_cited(grant_id);
CREATE INDEX IF NOT EXISTS idx_botanic_source ON botanic(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_grant_term_grant ON grant_term(grant_id);
CREATE INDEX IF NOT EXISTS idx_field_search_grant ON field_of_classification_search(grant_id);

-- Metadata indexes
CREATE INDEX IF NOT EXISTS idx_processed_file_filename ON processed_file(filename);
CREATE INDEX IF NOT EXISTS idx_processing_log_timestamp ON processing_log(timestamp);

-- Embedding indexes (partial — only rows that have embeddings)
CREATE INDEX IF NOT EXISTS idx_publication_abstract_embedding ON publication(abstract_embedding) WHERE abstract_embedding IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_grant_abstract_embedding ON grant(abstract_embedding) WHERE abstract_embedding IS NOT NULL;
"""

SEED_ASSIGNEE_ROLE_CODES = [
    ('02', 'original assignee'),
    ('03', 'subsequent assignee'),
    ('04', 'employer'),
    ('05', 'assignor'),
    ('06', 'assignor/employer'),
    ('07', 'obligated assignee'),
]

SEED_KIND_CODES = [
    # Publications
    ('A1', 'publication', 'published patent application (utility)'),
    ('A2', 'publication', 'republished patent application'),
    ('P1', 'publication', 'published plant patent application'),
    # Grants
    ('B1', 'grant', 'utility patent granted without previous publication'),
    ('B2', 'grant', 'utility patent granted with previous publication'),
    ('E1', 'grant', 'reissue patent'),
    ('S1', 'grant', 'design patent'),
    ('P2', 'grant', 'plant patent granted without previous publication'),
    ('P3', 'grant', 'plant patent granted with previous publication'),
    ('A', 'grant', 'statutory invention registration'),
    ('H', 'grant', 'defensive publication'),
    ('U1', 'grant', 'utility model'),
    ('Y1', 'grant', 'pre-grant publication (corrected)'),
    ('Y2', 'grant', 'pre-grant publication (original)'),
    ('C1', 'grant', 'corrected grant'),
    ('C2', 'grant', 'corrected grant (re-examination)'),
]


def init_db(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    cur.executescript(SCHEMA_SQL)

    # Migrate: add abstract_embedding column if missing (existing databases)
    for table in ("publication", "grant"):
        cols = [row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        if "abstract_embedding" not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN abstract_embedding BLOB")

    cur.executescript(INDEXES_SQL)

    # Seed lookup tables
    cur.executemany(
        "INSERT OR IGNORE INTO assignee_role_code (code, description) VALUES (?, ?)",
        SEED_ASSIGNEE_ROLE_CODES,
    )
    cur.executemany(
        "INSERT OR IGNORE INTO kind_code (code, dataset, description) VALUES (?, ?, ?)",
        SEED_KIND_CODES,
    )

    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Initialize bibliographic_data.db")
    parser.add_argument("--db", default="bibliographic_data.db", help="Path to SQLite database (default: %(default)s)")
    args = parser.parse_args()
    init_db(args.db)
    print(f"Database initialized: {args.db}")


if __name__ == "__main__":
    main()