# USPTO Bibliographic Data Mirror — Design Plan

## Overview

Mirror USPTO patent grant and publication bibliographic data from the USPTO Open Data Portal (ODP) bulk data API into a local SQLite database (`bibliographic_data.db`). The project lives in `/data/BiblioData/`.

## Datasets

| Dataset | API Product | Start Date | Sample File | Sample Records |
|---------|-------------|------------|-------------|----------------|
| Publications | APPBLXML | 2001-03-15 | ipab20260122_wk04.zip | ~5,903/week |
| Grants | PTBLXML | 2002-01-01 | ipgb20251223_wk51.zip | ~4,675/week |

## API Key Handling

1. Check `ODP_API_KEY` environment variable (primary)
2. Check `--api-key-file` CLI argument (secondary)
3. If neither present → fail with error: "Set ODP_API_KEY env var or provide --api-key-file"
4. No hardcoded default key file path (project must be portable)

---

## Phase 1: Project Setup & Database Schema

### Entrance Criteria
- Plan approved by user

### Steps
- [ ] 1.1 Create directory structure: `downloads/publication/`, `downloads/grant/`, `extracted/publication/`, `extracted/grant/`, `logs/`
- [ ] 1.2 Create `init_db.py` with full schema:
  - [ ] 1.2.1 Entity tables: `person`, `assignee`, `examiner`, `attorney_agent_firm`
  - [ ] 1.2.2 Main tables: `publication`, `grant`
  - [ ] 1.2.3 Junction tables: `publication_inventor`, `publication_applicant`, `publication_assignee`, `grant_inventor`, `grant_applicant`, `grant_assignee`, `grant_examiner`, `grant_attorney_agent`
  - [ ] 1.2.4 Classification tables: `classification_ipcr`, `classification_cpc`, `classification_national`, `classification_locarno`
  - [ ] 1.2.5 Supporting tables: `priority_claim`, `pct_filing_data`, `pct_publishing_data`, `related_document`, `reference_cited`, `botanic`, `grant_term`, `field_of_classification_search`
  - [ ] 1.2.6 Metadata tables: `processed_file`, `processing_log`
  - [ ] 1.2.7 Lookup tables: `assignee_role_code`, `kind_code`
  - [ ] 1.2.8 All indexes
- [ ] 1.3 Seed `assignee_role_code` (02-07) and `kind_code` tables
- [ ] 1.4 Verify idempotency: run `init_db.py` twice, no errors
- [ ] 1.5 Write schema validation tests:
  - [ ] 1.5.1 All tables exist
  - [ ] 1.5.2 All columns have correct names and types
  - [ ] 1.5.3 UNIQUE constraints work (insert duplicate → error or IGNORE)
  - [ ] 1.5.4 FK constraints are declared
  - [ ] 1.5.5 Indexes exist

### Exit Criteria
- `init_db.py` runs cleanly and creates all tables
- All schema tests pass
- Database is empty but structurally sound

---

## Phase 2: Small-Sample Unit Tests

### Entrance Criteria
- Phase 1 complete (all schema tests pass)

### Steps
- [ ] 2.1 Extract 10-record test fixtures:
  - [ ] 2.1.1 From ipab20260122_wk04.zip: extract 10 publication XML records into `tests/fixtures/publications_10.xml`
  - [ ] 2.1.2 From ipgb20251223_wk51.zip: extract 10 grant XML records into `tests/fixtures/grants_10.xml` (include 1 design patent, 1 plant patent, 1 reissue if possible, plus utility patents with varied features)
- [ ] 2.2 Write XML splitting tests:
  - [ ] 2.2.1 Multi-document XML splits correctly on `<?xml version` boundary
  - [ ] 2.2.2 Each split record is well-formed XML
  - [ ] 2.2.3 DOCTYPE lines are stripped
  - [ ] 2.2.4 Correct number of records extracted (10 for each fixture)
- [ ] 2.3 Write publication parser unit tests:
  - [ ] 2.3.1 publication-reference fields (country, doc_number, kind, pub_date)
  - [ ] 2.3.2 application-reference fields (appl_type, appl_doc_number, appl_date)
  - [ ] 2.3.3 series_code
  - [ ] 2.3.4 invention_title
  - [ ] 2.3.5 inventors (names, addresses, sequence)
  - [ ] 2.3.6 applicants (names, orgname, authority_category, app_type)
  - [ ] 2.3.7 assignees (orgname, role codes)
  - [ ] 2.3.8 IPCR classifications
  - [ ] 2.3.9 CPC classifications (main + further)
  - [ ] 2.3.10 priority claims
  - [ ] 2.3.11 PCT filing data
  - [ ] 2.3.12 related documents
  - [ ] 2.3.13 abstract text
- [ ] 2.4 Write grant parser unit tests (publication fields plus):
  - [ ] 2.4.1 examiners (primary + assistant)
  - [ ] 2.4.2 agents/attorneys (orgname, rep_type)
  - [ ] 2.4.3 references cited (patent citations + NPL)
  - [ ] 2.4.4 number_of_claims, exemplary_claim
  - [ ] 2.4.5 figures (drawing_sheets, figures_count)
  - [ ] 2.4.6 grant term (length_of_grant, term_extension)
  - [ ] 2.4.7 classification_locarno (design patents)
  - [ ] 2.4.8 classification_national
  - [ ] 2.4.9 field_of_classification_search
  - [ ] 2.4.10 PCT publishing data
  - [ ] 2.4.11 botanic (plant patents)
- [ ] 2.5 Write entity deduplication tests:
  - [ ] 2.5.1 Same person name+address → one person row
  - [ ] 2.5.2 Same person as inventor AND applicant → one person row
  - [ ] 2.5.3 Different address for same name → different person rows
  - [ ] 2.5.4 Orgname-based persons dedup correctly
- [ ] 2.6 Write junction table tests:
  - [ ] 2.6.1 Correct person_id references
  - [ ] 2.6.2 Sequence numbers preserved
  - [ ] 2.6.3 Role-specific fields on junction tables (authority_category, app_type)
  - [ ] 2.6.4 Assignee role codes on junction tables
- [ ] 2.7 Run full test suite: `pytest test_uspto.py -v`

### Exit Criteria
- All unit tests pass on 10-record fixtures
- XML splitting works correctly
- All parser functions produce correct output for test data
- Entity deduplication is verified

---

## Phase 3: Process Script — Publications

### Entrance Criteria
- Phase 2 complete (all 10-record unit tests pass)

### Steps
- [ ] 3.1 Implement XML splitting in `process_uspto.py`
- [ ] 3.2 Implement publication record parser (all fields from Phase 2.3)
- [ ] 3.3 Implement person deduplication logic (INSERT OR IGNORE on entity_hash)
- [ ] 3.4 Implement database insertion with transaction per file
- [ ] 3.5 Implement `processed_file` tracking
- [ ] 3.6 Implement `--delete-source-data` flag
- [ ] 3.7 Implement `--dataset publication` CLI interface
- [ ] 3.8 Process full ipab20260122_wk04.zip:
  - [ ] 3.8.1 Verify 5,903 records in publication table
  - [ ] 3.8.2 Spot-check 5 specific publications by doc_number
  - [ ] 3.8.3 Verify person, assignee, classification counts are reasonable
  - [ ] 3.8.4 Check for NULLs in NOT NULL columns
  - [ ] 3.8.5 Verify FK integrity (all junction table references resolve)
- [ ] 3.9 Re-run test suite: `pytest test_uspto.py -v`

### Exit Criteria
- Full sample publication zip processes without errors
- 5,903 records in publication table
- All junction tables populated correctly
- Entity deduplication working at scale

---

## Phase 4: Process Script — Grants

### Entrance Criteria
- Phase 3 complete (publications processing verified)

### Steps
- [ ] 4.1 Implement grant record parser (adds examiners, agents, references cited, figures, term, Locarno, etc.)
- [ ] 4.2 Implement `--dataset grant` CLI interface
- [ ] 4.3 Process full ipgb20251223_wk51.zip:
  - [ ] 4.3.1 Verify 4,675 records in grant table
  - [ ] 4.3.2 Spot-check 5 specific grants (including 1 design patent D-number, 1 plant patent PP-number)
  - [ ] 4.3.3 Verify examiner table populated (should have primary examiners for all 4,675 grants)
  - [ ] 4.3.4 Verify attorney_agent_firm table populated
  - [ ] 4.3.5 Verify reference_cited table populated
  - [ ] 4.3.6 Verify grant_term table for design patents (length_of_grant=15)
  - [ ] 4.3.7 Verify classification_locarno for design patents
  - [ ] 4.3.8 Check botanic table for plant patents
- [ ] 4.4 Verify shared person deduplication:
  - [ ] 4.4.1 Person appearing in both publications and grants = one person row
  - [ ] 4.4.2 Junction tables correctly link to the shared person
- [ ] 4.5 Re-run test suite: `pytest test_uspto.py -v`

### Exit Criteria
- Full sample grant zip processes without errors
- 4,675 records in grant table
- All grant-specific tables populated (examiners, agents, references, term, Locarno)
- Shared person deduplication verified across both datasets

---

## Phase 5: Download Script

### Entrance Criteria
- Phase 4 complete (both datasets processing correctly)

### Steps
- [ ] 5.1 Implement API query logic:
  - [ ] 5.1.1 Construct URL for APPBLXML / PTBLXML endpoints
  - [ ] 5.1.2 Parse JSON response to extract file download URLs
  - [ ] 5.1.3 Handle pagination / date-range responses
- [ ] 5.2 Implement date-range partitioning (automatic 10-week batches)
- [ ] 5.3 Implement zip download:
  - [ ] 5.3.1 Download to `downloads/{dataset}/`
  - [ ] 5.3.2 Extract XML to `extracted/{dataset}/`
  - [ ] 5.3.3 Skip rpt.html and lst.txt unless needed for verification
- [ ] 5.4 Implement rate limiting and retry logic (reuse patterns from fetch_uspto_xml.py)
- [ ] 5.5 Implement `--skip-existing` flag
- [ ] 5.6 Implement API key resolution: ODP_API_KEY env → --api-key-file → error
- [ ] 5.7 Implement CLI interface: `--dataset`, `--start-date`, `--end-date`, `--output-dir`, `--batch-weeks`, `--log-level`
- [ ] 5.8 Test with small date range (1 week):
  - [ ] 5.8.1 Set `ODP_API_KEY` env var
  - [ ] 5.8.2 `python download_uspto.py --dataset publication --start-date 2026-01-16 --end-date 2026-01-22`
  - [ ] 5.8.3 Verify zip downloaded and XML extracted
  - [ ] 5.8.4 Verify XML format matches expected structure
  - [ ] 5.8.5 Repeat for grants
- [ ] 5.9 Test error handling:
  - [ ] 5.9.1 Missing API key → clear error message
  - [ ] 5.9.2 Invalid date range → error
  - [ ] 5.9.3 Network timeout → retry

### Exit Criteria
- Download script pulls data from USPTO ODP API successfully
- Zip files downloaded and XML extracted
- Rate limiting and retry logic work
- API key resolution works (env var, CLI arg, error)

---

## Phase 6: Full Integration Test

### Entrance Criteria
- Phases 3-5 complete

### Steps
- [ ] 6.1 Download 1 week of fresh publications (not the sample week)
- [ ] 6.2 Download 1 week of fresh grants
- [ ] 6.3 Process both into database
- [ ] 6.4 Verify record counts match lst.txt counts from zips
- [ ] 6.5 Test `--delete-source-data` flag:
  - [ ] 6.5.1 Process with flag → source XML and zips deleted
  - [ ] 6.5.2 Database records remain intact after deletion
  - [ ] 6.5.3 `processed_file` entries exist for deleted files
- [ ] 6.6 Test idempotency: re-run process → no duplicate records
- [ ] 6.7 Run full test suite: `pytest test_uspto.py -v`

### Exit Criteria
- End-to-end pipeline works: download → process → verify → delete source
- No data loss when `--delete-source-data` is used
- Re-processing does not create duplicates

---

## Phase 7: Cron & Automation

### Entrance Criteria
- Phase 6 complete

### Steps
- [ ] 7.1 Create `run_weekly.sh`:
  - [ ] 7.1.1 Compute START_DATE as last Thursday
  - [ ] 7.1.2 Compute END_DATE as today (Wednesday)
  - [ ] 7.1.3 Call download for publications and grants
  - [ ] 7.1.4 Call process for publications and grants with `--delete-source-data`
  - [ ] 7.1.5 Ensure ODP_API_KEY is available (export or .env file)
  - [ ] 7.1.6 Append to continuous log `biblio_mirror.log`
- [ ] 7.2 Test wrapper manually:
  - [ ] 7.2.1 Run `bash run_weekly.sh`
  - [ ] 7.2.2 Verify dates computed correctly
  - [ ] 7.2.3 Verify download + process runs
  - [ ] 7.2.4 Verify logging output
- [ ] 7.3 Set up cron entry: `0 1 * * 3 sean /data/BiblioData/run_weekly.sh >> /data/BiblioData/biblio_mirror.log 2>&1`
- [ ] 7.4 Document setup requirements:
  - [ ] 7.4.1 ODP_API_KEY env var (how to get key, how to set)
  - [ ] 7.4.2 Python dependencies (lxml, requests)
  - [ ] 7.4.3 Initial load instructions
  - [ ] 7.4.4 Cron setup instructions

### Exit Criteria
- `run_weekly.sh` works manually
- Cron entry installed
- Setup documented

---

## Phase 8: Initial Bulk Load

### Entrance Criteria
- Phase 7 complete
- User confirms ready to proceed with full historical load

### Steps
- [ ] 8.1 Load publications: 2001-03-15 to present
  - [ ] 8.1.1 `python download_uspto.py --dataset publication --start-date 2001-03-15 --end-date 2026-04-25 --skip-existing`
  - [ ] 8.1.2 `python process_uspto.py --dataset publication`
  - [ ] 8.1.3 Verify total record count (~1,300 weeks × ~5,000/week ≈ 6.5M)
- [ ] 8.2 Load grants: 2002-01-01 to present
  - [ ] 8.2.1 `python download_uspto.py --dataset grant --start-date 2002-01-01 --end-date 2026-04-25 --skip-existing`
  - [ ] 8.2.2 `python process_uspto.py --dataset grant`
  - [ ] 8.2.3 Verify total record count (~1,250 weeks × ~4,500/week ≈ 5.6M)
- [ ] 8.3 Verify database integrity:
  - [ ] 8.3.1 All FK constraints satisfied
  - [ ] 8.3.2 No orphan junction rows
  - [ ] 8.3.3 All processed_file entries exist
- [ ] 8.4 Enable weekly cron for ongoing updates

### Exit Criteria
- Full historical data loaded
- Record counts are reasonable
- Weekly cron running for ongoing updates

---

## Database Schema Summary

### Entity Tables
- `person` (shared for inventors + applicants): id, last_name, first_name, suffix, orgname, city, state, country, entity_hash UNIQUE
- `assignee`: id, last_name, first_name, orgname, city, state, country, entity_hash UNIQUE
- `examiner`: id, last_name, first_name, department, examiner_type, entity_hash UNIQUE
- `attorney_agent_firm`: id, last_name, first_name, orgname, city, state, country, rep_type, entity_hash UNIQUE

### Main Tables
- `publication`: id, country, doc_number, kind, pub_date, appl_type, appl_doc_number, appl_date, series_code, invention_title, abstract_text, date_produced, dtd_version, file_reference
- `grant`: id, country, doc_number, kind, pub_date, appl_type, appl_doc_number, appl_date, series_code, invention_title, abstract_text, number_of_claims, exemplary_claim, number_of_drawing_sheets, number_of_figures, date_produced, dtd_version, file_reference

### Junction Tables
- `publication_inventor(publication_id, person_id, sequence, designation)`
- `publication_applicant(publication_id, person_id, sequence, app_type, authority_category, designation, residence_country)`
- `publication_assignee(publication_id, assignee_id, role, sequence)`
- `grant_inventor(grant_id, person_id, sequence, designation)`
- `grant_applicant(grant_id, person_id, sequence, app_type, authority_category, designation, residence_country)`
- `grant_assignee(grant_id, assignee_id, role, sequence)`
- `grant_examiner(grant_id, examiner_id, examiner_type)`
- `grant_attorney_agent(grant_id, attorney_agent_id, sequence)`

### Classification Tables
- `classification_ipcr(source_type, source_id, ipc_version_date, classification_level, section, ipc_class, subclass, main_group, subgroup, symbol_position, classification_value, action_date, generating_office_country, classification_status, classification_data_source)`
- `classification_cpc(source_type, source_id, cpc_version_date, section, cpc_class, subclass, main_group, subgroup, symbol_position, classification_value, action_date, generating_office_country, classification_status, classification_data_source, scheme_origination_code, is_main)`
- `classification_national(source_type, source_id, country, main_classification, additional_info)`
- `classification_locarno(grant_id, edition, main_classification)`

### Other Data Tables
- `priority_claim(source_type, source_id, sequence, kind, country, doc_number, date)`
- `pct_filing_data(source_type, source_id, country, doc_number, date, us_371c12_date)`
- `pct_publishing_data(source_type, source_id, country, doc_number, kind, date)`
- `related_document(source_type, source_id, relation_type, parent_country, parent_doc_number, parent_date, parent_status, parent_grant_doc_number, parent_grant_date, child_country, child_doc_number)`
- `reference_cited(grant_id, citation_num, citation_type, pat_country, pat_doc_number, pat_kind, pat_name, pat_date, npl_text, category, classification_cpc_text)`
- `botanic(source_type, source_id, latin_name, variety)`
- `grant_term(grant_id, length_of_grant, term_disclaimer)`
- `field_of_classification_search(grant_id, search_country, search_main_classification, search_additional_info, search_cpc_text)`

### Metadata/Lookup Tables
- `processed_file(filename, dataset, file_date, week_number, record_count, processed_at, sha256)`
- `processing_log(timestamp, level, dataset, message, detail)`
- `assignee_role_code(code, description)`
- `kind_code(code, dataset, description)`

---

## File Layout

```
/data/BiblioData/
├── design_plan.md              # This file
├── bibliographic_data.db       # SQLite database
├── biblio_mirror.log           # Continuous log
├── init_db.py                  # Database initialization
├── download_uspto.py           # Download script
├── process_uspto.py            # Processing script
├── run_weekly.sh               # Cron wrapper
├── test_uspto.py               # Test suite
├── pub-query.txt               # API query template
├── grant-query.txt             # API query template
├── ipab20260122_wk04.zip       # Sample publications
├── ipgb20251223_wk51.zip       # Sample grants
├── downloads/
│   ├── publication/
│   └── grant/
├── extracted/
│   ├── publication/
│   └── grant/
├── logs/
└── tests/
    ├── fixtures/
    │   ├── publications_10.xml
    │   └── grants_10.xml
    └── __init__.py
```