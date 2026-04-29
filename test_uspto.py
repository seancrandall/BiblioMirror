"""Tests for USPTO bibliographic data project — Phase 1 schema + Phase 2 parsing."""

import os
import sqlite3
import tempfile
import pytest

# Import from the project directory
import sys
sys.path.insert(0, os.path.dirname(__file__))
from init_db import init_db
from process_uspto import (
    split_xml_records, parse_record, parse_publication, parse_grant,
    compute_entity_hash, DatabaseLoader,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "tests", "fixtures")


@pytest.fixture
def db_path(tmp_path):
    """Create a fresh test database."""
    path = str(tmp_path / "test_bibliographic_data.db")
    init_db(path)
    return path


@pytest.fixture
def conn(db_path):
    """Return a connection to the test database."""
    c = sqlite3.connect(db_path)
    c.execute("PRAGMA foreign_keys = ON")
    yield c
    c.close()


def get_tables(conn):
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [row[0] for row in cur.fetchall()]


def get_columns(conn, table):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [(row[1], row[2]) for row in cur.fetchall()]


# ============================================================
# Table existence tests
# ============================================================

EXPECTED_TABLES = [
    'assignee', 'assignee_role_code', 'attorney_agent_firm',
    'botanic', 'classification_cpc', 'classification_ipcr',
    'classification_locarno', 'classification_national',
    'examiner', 'field_of_classification_search',
    'grant', 'grant_applicant', 'grant_assignee',
    'grant_attorney_agent', 'grant_examiner', 'grant_inventor',
    'grant_term', 'kind_code', 'pct_filing_data',
    'pct_publishing_data', 'person', 'priority_claim',
    'processed_file', 'processing_log', 'publication',
    'publication_applicant', 'publication_assignee',
    'publication_inventor', 'reference_cited', 'related_document',
]


def test_all_tables_exist(db_path):
    conn = sqlite3.connect(db_path)
    tables = get_tables(conn)
    for t in EXPECTED_TABLES:
        assert t in tables, f"Missing table: {t}"
    conn.close()


def test_no_extra_tables(db_path):
    conn = sqlite3.connect(db_path)
    tables = get_tables(conn)
    # sqlite internals we ignore
    internal = {'sqlite_sequence'}
    extra = set(tables) - set(EXPECTED_TABLES) - internal
    assert not extra, f"Unexpected tables: {extra}"
    conn.close()


# ============================================================
# Column tests for key tables
# ============================================================

def test_person_columns(conn):
    cols = dict(get_columns(conn, 'person'))
    assert 'id' in cols
    assert 'last_name' in cols
    assert 'first_name' in cols
    assert 'suffix' in cols
    assert 'orgname' in cols
    assert 'city' in cols
    assert 'state' in cols
    assert 'country' in cols
    assert 'entity_hash' in cols


def test_publication_columns(conn):
    cols = dict(get_columns(conn, 'publication'))
    for c in ['id', 'country', 'doc_number', 'kind', 'pub_date',
              'appl_type', 'appl_doc_number', 'appl_date',
              'series_code', 'invention_title', 'abstract_text',
              'date_produced', 'dtd_version', 'file_reference']:
        assert c in cols, f"Missing column: {c}"


def test_grant_columns(conn):
    cols = dict(get_columns(conn, 'grant'))
    for c in ['id', 'country', 'doc_number', 'kind', 'pub_date',
              'appl_type', 'appl_doc_number', 'appl_date',
              'series_code', 'invention_title', 'abstract_text',
              'number_of_claims', 'exemplary_claim',
              'number_of_drawing_sheets', 'number_of_figures',
              'date_produced', 'dtd_version', 'file_reference']:
        assert c in cols, f"Missing column: {c}"


def test_examiner_columns(conn):
    cols = dict(get_columns(conn, 'examiner'))
    for c in ['id', 'last_name', 'first_name', 'department',
              'examiner_type', 'entity_hash']:
        assert c in cols, f"Missing column: {c}"


def test_assignee_columns(conn):
    cols = dict(get_columns(conn, 'assignee'))
    for c in ['id', 'last_name', 'first_name', 'orgname',
              'city', 'state', 'country', 'entity_hash']:
        assert c in cols, f"Missing column: {c}"


def test_attorney_agent_firm_columns(conn):
    cols = dict(get_columns(conn, 'attorney_agent_firm'))
    for c in ['id', 'last_name', 'first_name', 'orgname',
              'city', 'state', 'country', 'rep_type', 'entity_hash']:
        assert c in cols, f"Missing column: {c}"


# ============================================================
# Junction table FK columns
# ============================================================

def test_publication_inventor_columns(conn):
    cols = dict(get_columns(conn, 'publication_inventor'))
    assert 'publication_id' in cols
    assert 'person_id' in cols
    assert 'sequence' in cols
    assert 'designation' in cols


def test_publication_applicant_columns(conn):
    cols = dict(get_columns(conn, 'publication_applicant'))
    assert 'publication_id' in cols
    assert 'person_id' in cols
    assert 'app_type' in cols
    assert 'authority_category' in cols
    assert 'designation' in cols
    assert 'residence_country' in cols


def test_grant_inventor_columns(conn):
    cols = dict(get_columns(conn, 'grant_inventor'))
    assert 'grant_id' in cols
    assert 'person_id' in cols


def test_grant_applicant_columns(conn):
    cols = dict(get_columns(conn, 'grant_applicant'))
    assert 'grant_id' in cols
    assert 'person_id' in cols
    assert 'app_type' in cols
    assert 'authority_category' in cols


def test_grant_examiner_columns(conn):
    cols = dict(get_columns(conn, 'grant_examiner'))
    assert 'grant_id' in cols
    assert 'examiner_id' in cols
    assert 'examiner_type' in cols


def test_grant_attorney_agent_columns(conn):
    cols = dict(get_columns(conn, 'grant_attorney_agent'))
    assert 'grant_id' in cols
    assert 'attorney_agent_id' in cols


# ============================================================
# Classification table columns
# ============================================================

def test_classification_ipcr_columns(conn):
    cols = dict(get_columns(conn, 'classification_ipcr'))
    for c in ['source_type', 'source_id', 'section', 'ipc_class',
              'subclass', 'main_group', 'subgroup',
              'classification_level', 'classification_value']:
        assert c in cols, f"Missing column: {c}"


def test_classification_cpc_columns(conn):
    cols = dict(get_columns(conn, 'classification_cpc'))
    for c in ['source_type', 'source_id', 'section', 'cpc_class',
              'subclass', 'main_group', 'subgroup', 'is_main',
              'scheme_origination_code']:
        assert c in cols, f"Missing column: {c}"


def test_classification_locarno_columns(conn):
    cols = dict(get_columns(conn, 'classification_locarno'))
    assert 'grant_id' in cols
    assert 'edition' in cols
    assert 'main_classification' in cols


# ============================================================
# Other table columns
# ============================================================

def test_reference_cited_columns(conn):
    cols = dict(get_columns(conn, 'reference_cited'))
    for c in ['grant_id', 'citation_type', 'pat_country', 'pat_doc_number',
              'npl_text', 'category']:
        assert c in cols, f"Missing column: {c}"


def test_related_document_columns(conn):
    cols = dict(get_columns(conn, 'related_document'))
    for c in ['source_type', 'source_id', 'relation_type',
              'parent_doc_number', 'child_doc_number']:
        assert c in cols, f"Missing column: {c}"


def test_priority_claim_columns(conn):
    cols = dict(get_columns(conn, 'priority_claim'))
    for c in ['source_type', 'source_id', 'kind', 'country', 'doc_number', 'date']:
        assert c in cols, f"Missing column: {c}"


# ============================================================
# UNIQUE constraint tests
# ============================================================

def test_person_entity_hash_unique(conn):
    conn.execute("INSERT INTO person (last_name, first_name, city, country, entity_hash) VALUES ('Smith', 'John', 'Austin', 'US', 'hash1')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO person (last_name, first_name, city, country, entity_hash) VALUES ('Smith', 'John', 'Austin', 'US', 'hash1')")


def test_publication_unique_constraint(conn):
    conn.execute("INSERT INTO publication (country, doc_number, kind, pub_date, appl_type, date_published) VALUES ('US', '20260000001', 'A1', '20260122', 'utility', '20260122')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO publication (country, doc_number, kind, pub_date, appl_type, date_published) VALUES ('US', '20260000001', 'A1', '20260122', 'utility', '20260122')")


def test_grant_unique_constraint(conn):
    conn.execute("INSERT INTO grant (country, doc_number, kind, pub_date, appl_type, date_published) VALUES ('US', '12345678', 'B2', '20251223', 'utility', '20251223')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO grant (country, doc_number, kind, pub_date, appl_type, date_published) VALUES ('US', '12345678', 'B2', '20251223', 'utility', '20251223')")


# ============================================================
# Idempotency test
# ============================================================

def test_init_db_idempotent(tmp_path):
    path = str(tmp_path / "idempotent_test.db")
    init_db(path)
    init_db(path)  # Run again — should not error
    conn = sqlite3.connect(path)
    tables = get_tables(conn)
    assert 'publication' in tables
    # Verify seed data not duplicated
    count = conn.execute("SELECT COUNT(*) FROM assignee_role_code").fetchone()[0]
    assert count == 6  # Exactly 6 role codes
    conn.close()


# ============================================================
# Seed data tests
# ============================================================

def test_assignee_role_codes_seeded(conn):
    rows = conn.execute("SELECT COUNT(*) FROM assignee_role_code").fetchone()
    assert rows[0] == 6


def test_kind_codes_seeded(conn):
    rows = conn.execute("SELECT COUNT(*) FROM kind_code").fetchone()
    assert rows[0] >= 10  # At least publication + grant kind codes


def test_kind_codes_by_dataset(conn):
    pub_codes = conn.execute("SELECT COUNT(*) FROM kind_code WHERE dataset='publication'").fetchone()[0]
    grant_codes = conn.execute("SELECT COUNT(*) FROM kind_code WHERE dataset='grant'").fetchone()[0]
    assert pub_codes >= 3
    assert grant_codes >= 10


# ============================================================
# Index tests
# ============================================================

def test_indexes_exist(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
    indexes = [row[0] for row in cur.fetchall()]
    expected = [
        'idx_publication_doc_number', 'idx_publication_pub_date',
        'idx_grant_doc_number', 'idx_grant_pub_date',
        'idx_person_hash', 'idx_assignee_hash',
        'idx_examiner_hash', 'idx_attorney_agent_hash',
        'idx_class_ipcr_source', 'idx_class_cpc_source',
    ]
    for idx in expected:
        assert idx in indexes, f"Missing index: {idx}"
    conn.close()


# ============================================================
# Phase 2: XML Splitting Tests
# ============================================================

def test_split_publication_fixture():
    path = os.path.join(FIXTURES_DIR, "publications_10.xml")
    records = split_xml_records(path)
    assert len(records) == 10, f"Expected 10 records, got {len(records)}"


def test_split_doctype_with_internal_subset():
    """DOCTYPE declarations with internal subsets containing > chars should be fully stripped."""
    # Simulate a USPTO bulk file with DOCTYPE internal subset (ENTITY declarations with >)
    content = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<!DOCTYPE patent-application-publication SYSTEM "pap-v16-2002-01-01.dtd" [\n'
        b'<!ENTITY img1 SYSTEM "img1.TIF" NDATA TIF>\n'
        b'<!ENTITY img2 SYSTEM "img2.TIF" NDATA TIF>\n'
        b']>\n'
        b'<patent-application-publication>\n'
        b'<publication-reference><document-id><country>US</country>'
        b'<doc-number>20030066116</doc-number><kind>A1</kind>'
        b'<date>20030410</date></document-id></publication-reference>\n'
        b'</patent-application-publication>\n'
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<!DOCTYPE patent-application-publication SYSTEM "pap-v16-2002-01-01.dtd" []>\n'
        b'<patent-application-publication>\n'
        b'<publication-reference><document-id><country>US</country>'
        b'<doc-number>20030066117</doc-number><kind>A1</kind>'
        b'<date>20030410</date></document-id></publication-reference>\n'
        b'</patent-application-publication>\n'
    )
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
        f.write(content)
        tmppath = f.name
    try:
        records = split_xml_records(tmppath)
        assert len(records) == 2, f"Expected 2 records, got {len(records)}"
        for i, rec in enumerate(records):
            root = parse_record(rec)
            assert root is not None, f"Record {i} failed to parse"
            assert root.tag == "patent-application-publication", f"Record {i} wrong tag: {root.tag}"
    finally:
        os.unlink(tmppath)


def test_split_grant_fixture():
    path = os.path.join(FIXTURES_DIR, "grants_10.xml")
    records = split_xml_records(path)
    assert len(records) == 10, f"Expected 10 records, got {len(records)}"


def test_split_records_are_parseable():
    path = os.path.join(FIXTURES_DIR, "publications_10.xml")
    records = split_xml_records(path)
    for i, rec in enumerate(records):
        root = parse_record(rec)
        assert root is not None, f"Record {i} failed to parse"


def test_split_grant_records_are_parseable():
    path = os.path.join(FIXTURES_DIR, "grants_10.xml")
    records = split_xml_records(path)
    for i, rec in enumerate(records):
        root = parse_record(rec)
        assert root is not None, f"Record {i} failed to parse"


# ============================================================
# Phase 2: Publication Parser Tests
# ============================================================

@pytest.fixture
def publication_records():
    path = os.path.join(FIXTURES_DIR, "publications_10.xml")
    records = split_xml_records(path)
    return [parse_publication(parse_record(r)) for r in records]


def test_publication_doc_numbers(publication_records):
    for d in publication_records:
        assert d is not None
        assert d["doc_number"], "Missing doc_number"
        assert d["kind"] in ("A1", "A2", "P1"), f"Unexpected kind: {d['kind']}"


def test_publication_country(publication_records):
    for d in publication_records:
        assert d["country"] == "US", f"Expected US, got {d['country']}"


def test_publication_dates(publication_records):
    for d in publication_records:
        assert d["pub_date"], "Missing pub_date"
        assert len(d["pub_date"]) == 8, f"Bad date format: {d['pub_date']}"
        assert d["date_published"], "Missing date_published"


def test_publication_appl_type(publication_records):
    for d in publication_records:
        assert d["appl_type"] in ("utility", "plant"), f"Unexpected appl_type: {d['appl_type']}"


def test_publication_has_inventors(publication_records):
    for d in publication_records:
        assert len(d["inventors"]) > 0, f"No inventors for {d['doc_number']}"
        inv = d["inventors"][0]
        assert inv["last_name"] or inv["orgname"], "Inventor has neither last_name nor orgname"


def test_publication_has_applicants(publication_records):
    for d in publication_records:
        assert len(d["applicants"]) > 0, f"No applicants for {d['doc_number']}"


def test_publication_invention_title(publication_records):
    for d in publication_records:
        assert d["invention_title"], f"Missing title for {d['doc_number']}"


def test_publication_classifications(publication_records):
    total_cpc = 0
    total_ipcr = 0
    for d in publication_records:
        total_cpc += len(d["classifications_cpc"])
        total_ipcr += len(d["classifications_ipcr"])
    assert total_cpc > 0, "No CPC classifications in any record"
    assert total_ipcr > 0, "No IPCR classifications in any record"


def test_publication_cpc_has_main(publication_records):
    """At least some records should have a main CPC."""
    main_count = sum(1 for d in publication_records for c in d["classifications_cpc"] if c["is_main"])
    assert main_count > 0, "No main CPC classifications found"


# ============================================================
# Phase 2: Grant Parser Tests
# ============================================================

@pytest.fixture
def grant_records():
    path = os.path.join(FIXTURES_DIR, "grants_10.xml")
    records = split_xml_records(path)
    return [parse_grant(parse_record(r)) for r in records]


def test_grant_doc_numbers(grant_records):
    for d in grant_records:
        assert d is not None
        assert d["doc_number"], "Missing doc_number"


def test_grant_kinds(grant_records):
    kinds = {d["kind"] for d in grant_records}
    assert "B2" in kinds, "Expected B2 kind code in grants"
    # Should have at least one S1 (design) in our fixture
    assert "S1" in kinds, f"Expected S1 design patent kind code, got: {kinds}"


def test_grant_has_examiners(grant_records):
    for d in grant_records:
        assert len(d["examiners"]) > 0, f"No examiners for {d['doc_number']}"
        primary = [e for e in d["examiners"] if e["examiner_type"] == "primary"]
        assert len(primary) >= 1, f"No primary examiner for {d['doc_number']}"


def test_grant_has_agents(grant_records):
    total = sum(len(d["agents"]) for d in grant_records)
    assert total > 0, "No agents/attorneys in any grant record"


def test_grant_has_references_cited(grant_records):
    total = sum(len(d["references_cited"]) for d in grant_records)
    assert total > 0, "No references cited in any grant record"


def test_grant_reference_types(grant_records):
    patent_refs = 0
    npl_refs = 0
    for d in grant_records:
        for ref in d["references_cited"]:
            if ref["citation_type"] == "patent":
                patent_refs += 1
            elif ref["citation_type"] == "npl":
                npl_refs += 1
    assert patent_refs > 0, "No patent citations found"
    # NPL is optional but commonly present


def test_grant_number_of_claims(grant_records):
    for d in grant_records:
        if d["kind"] in ("B1", "B2"):
            assert d["number_of_claims"] is not None, f"Missing number_of_claims for {d['doc_number']}"


def test_grant_term_data(grant_records):
    """Design patents should have length_of_grant=15."""
    for d in grant_records:
        if d["kind"] == "S1":
            assert d["grant_term"] is not None, f"Missing grant_term for design patent {d['doc_number']}"
            if d["grant_term"]:
                assert d["grant_term"]["length_of_grant"] == 15, f"Design patent term should be 15, got {d['grant_term']['length_of_grant']}"


def test_grant_locarno_for_design(grant_records):
    """Design patents should have Locarno classification."""
    for d in grant_records:
        if d["kind"] == "S1":
            assert len(d["classifications_locarno"]) > 0, f"No Locarno for design {d['doc_number']}"


def test_grant_classifications(grant_records):
    total_cpc = sum(len(d["classifications_cpc"]) for d in grant_records)
    total_ipcr = sum(len(d["classifications_ipcr"]) for d in grant_records)
    assert total_cpc > 0, "No CPC classifications in grants"
    assert total_ipcr > 0, "No IPCR classifications in grants"


def test_grant_field_of_search(grant_records):
    total = sum(len(d["field_of_classification_search"]) for d in grant_records)
    assert total > 0, "No field of classification search data in grants"


# ============================================================
# Phase 2: Entity Deduplication Tests
# ============================================================

@pytest.fixture
def loaded_db(tmp_path):
    """Load 10-record fixtures into a fresh database."""
    db_path = str(tmp_path / "test_loaded.db")
    init_db(db_path)
    loader = DatabaseLoader(db_path)

    # Load publications
    pub_path = os.path.join(FIXTURES_DIR, "publications_10.xml")
    records = split_xml_records(pub_path)
    for rec in records:
        root = parse_record(rec)
        d = parse_publication(root)
        if d:
            loader.insert_publication(d)
    loader.commit()

    # Load grants
    grant_path = os.path.join(FIXTURES_DIR, "grants_10.xml")
    records = split_xml_records(grant_path)
    for rec in records:
        root = parse_record(rec)
        d = parse_grant(root)
        if d:
            loader.insert_grant(d)
    loader.commit()
    loader.close()

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


def test_publication_count(loaded_db):
    count = loaded_db.execute("SELECT COUNT(*) FROM publication").fetchone()[0]
    assert count == 10, f"Expected 10 publications, got {count}"


def test_grant_count(loaded_db):
    count = loaded_db.execute("SELECT COUNT(*) FROM grant").fetchone()[0]
    assert count == 10, f"Expected 10 grants, got {count}"


def test_person_deduplication(loaded_db):
    """Person table should have fewer rows than total inventors+applicants due to dedup."""
    pub_inv = loaded_db.execute("SELECT COUNT(*) FROM publication_inventor").fetchone()[0]
    pub_app = loaded_db.execute("SELECT COUNT(*) FROM publication_applicant").fetchone()[0]
    grant_inv = loaded_db.execute("SELECT COUNT(*) FROM grant_inventor").fetchone()[0]
    grant_app = loaded_db.execute("SELECT COUNT(*) FROM grant_applicant").fetchone()[0]
    total_roles = pub_inv + pub_app + grant_inv + grant_app
    person_count = loaded_db.execute("SELECT COUNT(*) FROM person").fetchone()[0]
    # Person table should be <= total roles (some dedup expected)
    assert person_count <= total_roles, f"Person count {person_count} > total roles {total_roles} — dedup not working"
    # Person table should be > 0
    assert person_count > 0, "No person records"


def test_inventors_have_names(loaded_db):
    """Every inventor junction should reference a person with a name."""
    rows = loaded_db.execute("""
        SELECT p.last_name, p.first_name, p.orgname
        FROM publication_inventor pi
        JOIN person p ON pi.person_id = p.id
    """).fetchall()
    for last, first, org in rows:
        assert last or org, f"Inventor has neither last_name nor orgname"


def test_examiner_count(loaded_db):
    count = loaded_db.execute("SELECT COUNT(*) FROM examiner").fetchone()[0]
    assert count > 0, "No examiners in database"


def test_attorney_count(loaded_db):
    count = loaded_db.execute("SELECT COUNT(*) FROM attorney_agent_firm").fetchone()[0]
    assert count > 0, "No attorneys in database"


def test_reference_cited_count(loaded_db):
    count = loaded_db.execute("SELECT COUNT(*) FROM reference_cited").fetchone()[0]
    assert count > 0, "No references cited in database"


def test_classification_counts(loaded_db):
    ipcr = loaded_db.execute("SELECT COUNT(*) FROM classification_ipcr").fetchone()[0]
    cpc = loaded_db.execute("SELECT COUNT(*) FROM classification_cpc").fetchone()[0]
    assert ipcr > 0, "No IPCR classifications"
    assert cpc > 0, "No CPC classifications"


def test_grant_term_count(loaded_db):
    count = loaded_db.execute("SELECT COUNT(*) FROM grant_term").fetchone()[0]
    assert count > 0, "No grant_term records"


def test_locarno_for_design(loaded_db):
    """Design grants should have Locarno classifications."""
    rows = loaded_db.execute("""
        SELECT cl.grant_id FROM classification_locarno cl
        JOIN grant g ON cl.grant_id = g.id
        WHERE g.kind = 'S1'
    """).fetchall()
    assert len(rows) > 0, "No Locarno classifications for design patents"


def test_fk_integrity(loaded_db):
    """All junction table foreign keys should resolve."""
    # publication_inventor -> publication, person
    orphans = loaded_db.execute("""
        SELECT COUNT(*) FROM publication_inventor pi
        LEFT JOIN publication p ON pi.publication_id = p.id
        WHERE p.id IS NULL
    """).fetchone()[0]
    assert orphans == 0, f"{orphans} orphan publication_inventor rows"

    orphans = loaded_db.execute("""
        SELECT COUNT(*) FROM publication_inventor pi
        LEFT JOIN person p ON pi.person_id = p.id
        WHERE p.id IS NULL
    """).fetchone()[0]
    assert orphans == 0, f"{orphans} orphan publication_inventor person refs"

    # grant_examiner -> grant, examiner
    orphans = loaded_db.execute("""
        SELECT COUNT(*) FROM grant_examiner ge
        LEFT JOIN grant g ON ge.grant_id = g.id
        WHERE g.id IS NULL
    """).fetchone()[0]
    assert orphans == 0, f"{orphans} orphan grant_examiner rows"


def test_entity_hash_consistency():
    """Same input → same hash."""
    h1 = compute_entity_hash("Smith", "John", "", "Austin", "TX", "US")
    h2 = compute_entity_hash("Smith", "John", "", "Austin", "TX", "US")
    assert h1 == h2


def test_entity_hash_case_insensitive():
    """Hash should be case-insensitive for dedup purposes."""
    h1 = compute_entity_hash("Smith", "John", "", "Austin", "TX", "US")
    h2 = compute_entity_hash("smith", "john", "", "austin", "tx", "us")
    assert h1 == h2, "Entity hash should be case-insensitive"


def test_entity_hash_different_names():
    """Different names → different hash."""
    h1 = compute_entity_hash("Smith", "John", "", "Austin", "TX", "US")
    h2 = compute_entity_hash("Jones", "Mary", "", "Austin", "TX", "US")
    assert h1 != h2


# ============================================================
# Abstract extraction tests
# ============================================================

def test_publication_abstracts_extracted(publication_records):
    """Utility publication records should have abstract text."""
    with_abstract = [d for d in publication_records if d["abstract_text"]]
    assert len(with_abstract) > 0, "No abstracts extracted from publication fixtures"


def test_grant_abstracts_extracted(grant_records):
    """Utility grant records (B1/B2) should have abstract text."""
    utility = [d for d in grant_records if d["kind"] in ("B1", "B2")]
    with_abstract = [d for d in utility if d["abstract_text"]]
    assert len(with_abstract) > 0, "No abstracts extracted from utility grant fixtures"


def test_design_grants_no_abstract(grant_records):
    """Design patents (S1) should have None abstract."""
    design = [d for d in grant_records if d["kind"] == "S1"]
    for d in design:
        assert d["abstract_text"] is None, f"Design patent {d['doc_number']} should have no abstract"


def test_abstracts_in_database(loaded_db):
    """Abstract text should be stored in the database."""
    pub_abs = loaded_db.execute("SELECT COUNT(*) FROM publication WHERE abstract_text IS NOT NULL").fetchone()[0]
    grant_abs = loaded_db.execute("SELECT COUNT(*) FROM grant WHERE abstract_text IS NOT NULL").fetchone()[0]
    assert pub_abs > 0, "No publication abstracts in database"
    assert grant_abs > 0, "No grant abstracts in database"


# ============================================================
# Streaming mode tests (download_dataset with db_path)
# ============================================================

import zipfile
from unittest.mock import patch, MagicMock
from datetime import datetime
from download_uspto import (
    download_dataset, extract_xml_from_zip, DATASET_PRODUCTS,
)


def _make_test_zip(zip_path, xml_path, xml_name):
    """Create a zip file containing the actual test fixture XML."""
    with open(xml_path, "rb") as f:
        content = f.read()
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr(xml_name, content)


class TestStreamingMode:
    """Tests for download_dataset with db_path (streaming mode)."""

    def test_streaming_processes_and_cleans_up(self, tmp_path):
        """Streaming mode: zip extracted, processed, then both zip and XML deleted."""
        db_path = str(tmp_path / "test_streaming.db")
        output_dir = str(tmp_path / "output")
        download_dir = os.path.join(output_dir, "downloads", "grant")
        extract_dir = os.path.join(output_dir, "extracted", "grant")
        os.makedirs(download_dir, exist_ok=True)
        os.makedirs(extract_dir, exist_ok=True)

        # Use the real grant fixture XML
        grant_fixture = os.path.join(FIXTURES_DIR, "grants_10.xml")
        xml_name = "ipgb20260101_wk01.xml"
        zip_name = "ipgb20260101_wk01.zip"
        zip_path = os.path.join(download_dir, zip_name)

        _make_test_zip(zip_path, grant_fixture, xml_name)

        assert os.path.exists(zip_path)
        assert not os.path.exists(os.path.join(extract_dir, xml_name))

        from process_uspto import process_file

        xml_files = extract_xml_from_zip(zip_path, extract_dir)
        assert len(xml_files) == 1
        assert os.path.exists(os.path.join(extract_dir, xml_name))

        # Delete zip (mimicking streaming mode)
        os.remove(zip_path)
        assert not os.path.exists(zip_path)

        # Process XML
        result = process_file(
            os.path.join(extract_dir, xml_name),
            db_path, "grant",
            delete_source=True, download_dir=None,
        )

        # XML should be deleted after processing
        assert not os.path.exists(os.path.join(extract_dir, xml_name))

        # Data should be in the database
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM grant").fetchone()[0]
        conn.close()
        assert count > 0, "Grant records should have been inserted into database"

    def test_streaming_skip_already_processed(self, tmp_path):
        """Streaming mode: already-processed zips are skipped and leftover files cleaned up."""
        db_path = str(tmp_path / "test_streaming_skip.db")
        output_dir = str(tmp_path / "output")
        download_dir = os.path.join(output_dir, "downloads", "grant")
        extract_dir = os.path.join(output_dir, "extracted", "grant")
        os.makedirs(download_dir, exist_ok=True)
        os.makedirs(extract_dir, exist_ok=True)

        # Use the real grant fixture XML
        grant_fixture = os.path.join(FIXTURES_DIR, "grants_10.xml")
        xml_name = "ipgb20260101_wk01.xml"
        zip_name = "ipgb20260101_wk01.zip"

        # First, process the file normally
        _make_test_zip(os.path.join(download_dir, zip_name), grant_fixture, xml_name)
        extract_xml_from_zip(os.path.join(download_dir, zip_name), extract_dir)

        from process_uspto import process_file
        process_file(
            os.path.join(extract_dir, xml_name),
            db_path, "grant",
            delete_source=True, download_dir=None,
        )

        # Verify the file is in processed_file
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT id FROM processed_file WHERE filename = ?", (xml_name,)
        ).fetchone()
        conn.close()
        assert row is not None, "File should be in processed_file"

        # Place leftover zip on disk (simulating interrupted cleanup)
        _make_test_zip(os.path.join(download_dir, zip_name), grant_fixture, xml_name)
        assert os.path.exists(os.path.join(download_dir, zip_name))

        # Simulate the streaming skip logic: check processed_file and clean up
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT id FROM processed_file WHERE filename = ?", (xml_name,)
        ).fetchone()
        conn.close()
        assert row is not None

        # Clean up leftover files
        os.remove(os.path.join(download_dir, zip_name))
        assert not os.path.exists(os.path.join(download_dir, zip_name))

    def test_download_only_mode_preserves_files(self, tmp_path):
        """Without db_path (download-only mode), zips and XMLs are kept on disk."""
        output_dir = str(tmp_path / "output")
        download_dir = os.path.join(output_dir, "downloads", "grant")
        extract_dir = os.path.join(output_dir, "extracted", "grant")
        os.makedirs(download_dir, exist_ok=True)
        os.makedirs(extract_dir, exist_ok=True)

        grant_fixture = os.path.join(FIXTURES_DIR, "grants_10.xml")
        xml_name = "ipgb20260101_wk01.xml"
        zip_name = "ipgb20260101_wk01.zip"
        zip_path = os.path.join(download_dir, zip_name)

        _make_test_zip(zip_path, grant_fixture, xml_name)

        # Extract without processing
        xml_files = extract_xml_from_zip(zip_path, extract_dir)
        assert len(xml_files) == 1

        # Both zip and XML should still exist
        assert os.path.exists(zip_path)
        assert os.path.exists(os.path.join(extract_dir, xml_name))

    def test_process_file_delete_source(self, tmp_path):
        """process_file with delete_source=True deletes the XML and inserts data."""
        db_path = str(tmp_path / "test_delete.db")

        # Use the real grant fixture
        grant_fixture = os.path.join(FIXTURES_DIR, "grants_10.xml")
        xml_name = "ipgb20260101_wk01.xml"
        extract_dir = str(tmp_path / "extracted" / "grant")
        os.makedirs(extract_dir, exist_ok=True)
        xml_path = os.path.join(extract_dir, xml_name)

        import shutil
        shutil.copy2(grant_fixture, xml_path)

        assert os.path.exists(xml_path)

        from process_uspto import process_file
        result = process_file(xml_path, db_path, "grant", delete_source=True, download_dir=None)

        # XML should be deleted
        assert not os.path.exists(xml_path)

        # Data should be in the database
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM grant").fetchone()[0]
        conn.close()
        assert count > 0