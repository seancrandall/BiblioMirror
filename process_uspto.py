#!/usr/bin/env python3
"""Parse USPTO bibliographic XML files and load into SQLite database."""

import argparse
import hashlib
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from lxml import etree

# ============================================================
# Logging
# ============================================================

LOG_FORMAT = "%(asctime)s %(levelname)s: %(message)s"


def setup_logging(logfile=None, level=logging.INFO):
    handlers = [logging.StreamHandler(sys.stdout)]
    if logfile:
        handlers.append(logging.FileHandler(logfile, mode="a"))
    logging.basicConfig(format=LOG_FORMAT, level=level, handlers=handlers)


# ============================================================
# XML Splitting
# ============================================================

def split_xml_records(filepath):
    """Split a multi-document XML file into individual record strings.

    USPTO bulk XML files contain multiple concatenated XML documents,
    each with its own <?xml ...> declaration and <!DOCTYPE ...> line.
    """
    with open(filepath, "rb") as f:
        content = f.read()

    # Split on <?xml version boundary
    parts = re.split(rb"<\?xml version", content)
    records = []
    for part in parts[1:]:  # First part is empty/preamble
        record = b"<?xml version" + part
        # Strip DOCTYPE line
        record = re.sub(rb"<!DOCTYPE[^>]*>\s*", b"", record, count=1)
        # Strip any remaining XML declaration whitespace issues
        record = record.strip()
        if record:
            records.append(record)
    return records


def parse_record(xml_bytes):
    """Parse a single XML record string into an lxml Element tree."""
    return etree.fromstring(xml_bytes)


# ============================================================
# Text helpers
# ============================================================

def text(element, path, default=None):
    """Extract text from an XPath in an element, returning default if not found."""
    node = element.find(path)
    if node is not None and node.text:
        return node.text.strip()
    return default


def attr(element, path, name, default=None):
    """Extract an attribute from the element at the given path."""
    node = element.find(path)
    if node is not None:
        return node.get(name, default)
    return default


# ============================================================
# Entity hash computation
# ============================================================

def compute_entity_hash(*fields):
    """Compute a deterministic hash from entity fields for deduplication."""
    raw = "|".join(f.lower().strip() if f else "" for f in fields)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ============================================================
# Publication parser
# ============================================================

def parse_publication(root):
    """Parse a <us-patent-application> element into a dict."""
    bib = root.find("us-bibliographic-data-application")
    if bib is None:
        return None

    d = {}

    # Root element attributes
    d["file_reference"] = root.get("file")
    d["date_produced"] = root.get("date-produced")
    d["date_published"] = root.get("date-publ")
    d["dtd_version"] = root.get("dtd-version")

    # publication-reference / document-id
    pub_ref = bib.find("publication-reference/document-id")
    if pub_ref is not None:
        d["country"] = text(pub_ref, "country", "")
        d["doc_number"] = text(pub_ref, "doc-number", "")
        d["kind"] = text(pub_ref, "kind", "")
        d["pub_date"] = text(pub_ref, "date", "")
    else:
        d["country"] = ""
        d["doc_number"] = ""
        d["kind"] = ""
        d["pub_date"] = ""

    # application-reference / document-id
    app_ref = bib.find("application-reference")
    if app_ref is not None:
        d["appl_type"] = app_ref.get("appl-type", "")
        app_doc = app_ref.find("document-id")
        if app_doc is not None:
            d["appl_country"] = text(app_doc, "country")
            d["appl_doc_number"] = text(app_doc, "doc-number")
            d["appl_date"] = text(app_doc, "date")
        else:
            d["appl_country"] = None
            d["appl_doc_number"] = None
            d["appl_date"] = None
    else:
        d["appl_type"] = ""
        d["appl_country"] = None
        d["appl_doc_number"] = None
        d["appl_date"] = None

    d["series_code"] = text(bib, "us-application-series-code")

    # invention-title
    d["invention_title"] = text(bib, "invention-title")

    # abstract
    abstract_el = bib.find("abstract")
    if abstract_el is not None:
        paragraphs = [p.text.strip() for p in abstract_el.findall("p") if p.text]
        d["abstract_text"] = " ".join(paragraphs) if paragraphs else None
    else:
        d["abstract_text"] = None

    # --- Repeatable elements ---

    # Inventors
    d["inventors"] = []
    inventors_el = bib.find("us-parties/inventors")
    if inventors_el is not None:
        for inv in inventors_el.findall("inventor"):
            ab = inv.find("addressbook")
            if ab is None:
                continue
            inv_data = {
                "last_name": text(ab, "last-name"),
                "first_name": text(ab, "first-name"),
                "suffix": text(ab, "suffix"),
                "orgname": text(ab, "orgname"),
                "city": text(ab.find("address"), "city") if ab.find("address") is not None else None,
                "state": text(ab.find("address"), "state") if ab.find("address") is not None else None,
                "country": text(ab.find("address"), "country") if ab.find("address") is not None else None,
                "sequence": inv.get("sequence"),
                "designation": inv.get("designation"),
            }
            d["inventors"].append(inv_data)

    # Applicants
    d["applicants"] = []
    applicants_el = bib.find("us-parties/us-applicants")
    if applicants_el is not None:
        for app in applicants_el.findall("us-applicant"):
            ab = app.find("addressbook")
            if ab is None:
                continue
            addr = ab.find("address")
            app_data = {
                "last_name": text(ab, "last-name"),
                "first_name": text(ab, "first-name"),
                "orgname": text(ab, "orgname"),
                "city": text(addr, "city") if addr is not None else None,
                "state": text(addr, "state") if addr is not None else None,
                "country": text(addr, "country") if addr is not None else None,
                "sequence": app.get("sequence"),
                "app_type": app.get("app-type"),
                "authority_category": app.get("applicant-authority-category"),
                "designation": app.get("designation"),
                "residence_country": text(ab.find("residence"), "country") if ab.find("residence") is not None else None,
            }
            d["applicants"].append(app_data)

    # Assignees
    d["assignees"] = []
    assignees_el = bib.find("assignees")
    if assignees_el is not None:
        for idx, asg in enumerate(assignees_el.findall("assignee")):
            ab = asg.find("addressbook")
            if ab is None:
                continue
            addr = ab.find("address")
            asg_data = {
                "last_name": text(ab, "last-name"),
                "first_name": text(ab, "first-name"),
                "orgname": text(ab, "orgname"),
                "city": text(addr, "city") if addr is not None else None,
                "state": text(addr, "state") if addr is not None else None,
                "country": text(addr, "country") if addr is not None else None,
                "role": text(ab, "role"),
                "sequence": idx,
            }
            d["assignees"].append(asg_data)

    # IPCR classifications
    d["classifications_ipcr"] = _parse_classifications_ipcr(bib)

    # CPC classifications
    d["classifications_cpc"] = _parse_classifications_cpc(bib)

    # National classifications
    d["classifications_national"] = _parse_classifications_national(bib)

    # Priority claims
    d["priority_claims"] = _parse_priority_claims(bib)

    # PCT filing data
    d["pct_filing"] = _parse_pct_filing(bib)

    # Related documents
    d["related_documents"] = _parse_related_documents(bib)

    # Botanic
    d["botanic"] = _parse_botanic(bib)

    return d


# ============================================================
# Grant parser
# ============================================================

def parse_grant(root):
    """Parse a <us-patent-grant> element into a dict."""
    bib = root.find("us-bibliographic-data-grant")
    if bib is None:
        return None

    # Start with publication-like fields
    d = {}

    # Root element attributes
    d["file_reference"] = root.get("file")
    d["date_produced"] = root.get("date-produced")
    d["date_published"] = root.get("date-publ")
    d["dtd_version"] = root.get("dtd-version")

    # publication-reference / document-id
    pub_ref = bib.find("publication-reference/document-id")
    if pub_ref is not None:
        d["country"] = text(pub_ref, "country", "")
        d["doc_number"] = text(pub_ref, "doc-number", "")
        d["kind"] = text(pub_ref, "kind", "")
        d["pub_date"] = text(pub_ref, "date", "")
    else:
        d["country"] = ""
        d["doc_number"] = ""
        d["kind"] = ""
        d["pub_date"] = ""

    # application-reference / document-id
    app_ref = bib.find("application-reference")
    if app_ref is not None:
        d["appl_type"] = app_ref.get("appl-type", "")
        app_doc = app_ref.find("document-id")
        if app_doc is not None:
            d["appl_country"] = text(app_doc, "country")
            d["appl_doc_number"] = text(app_doc, "doc-number")
            d["appl_date"] = text(app_doc, "date")
        else:
            d["appl_country"] = None
            d["appl_doc_number"] = None
            d["appl_date"] = None
    else:
        d["appl_type"] = ""
        d["appl_country"] = None
        d["appl_doc_number"] = None
        d["appl_date"] = None

    d["series_code"] = text(bib, "us-application-series-code")
    d["invention_title"] = text(bib, "invention-title")

    # Grant-specific fields
    d["number_of_claims"] = None
    noc = text(bib, "number-of-claims")
    if noc:
        try:
            d["number_of_claims"] = int(noc)
        except ValueError:
            pass

    d["exemplary_claim"] = None
    ec = text(bib, "us-exemplary-claim")
    if ec:
        try:
            d["exemplary_claim"] = int(ec)
        except ValueError:
            pass

    # Figures
    figures_el = bib.find("figures")
    if figures_el is not None:
        nds = text(figures_el, "number-of-drawing-sheets")
        nf = text(figures_el, "number-of-figures")
        d["number_of_drawing_sheets"] = int(nds) if nds else None
        d["number_of_figures"] = int(nf) if nf else None
    else:
        d["number_of_drawing_sheets"] = None
        d["number_of_figures"] = None

    # Abstract
    abstract_el = bib.find("abstract")
    if abstract_el is not None:
        paragraphs = [p.text.strip() for p in abstract_el.findall("p") if p.text]
        d["abstract_text"] = " ".join(paragraphs) if paragraphs else None
    else:
        d["abstract_text"] = None

    # Inventors
    d["inventors"] = []
    inventors_el = bib.find("us-parties/inventors")
    if inventors_el is not None:
        for inv in inventors_el.findall("inventor"):
            ab = inv.find("addressbook")
            if ab is None:
                continue
            addr = ab.find("address")
            inv_data = {
                "last_name": text(ab, "last-name"),
                "first_name": text(ab, "first-name"),
                "suffix": text(ab, "suffix"),
                "orgname": text(ab, "orgname"),
                "city": text(addr, "city") if addr is not None else None,
                "state": text(addr, "state") if addr is not None else None,
                "country": text(addr, "country") if addr is not None else None,
                "sequence": inv.get("sequence"),
                "designation": inv.get("designation"),
            }
            d["inventors"].append(inv_data)

    # Applicants
    d["applicants"] = []
    applicants_el = bib.find("us-parties/us-applicants")
    if applicants_el is not None:
        for app in applicants_el.findall("us-applicant"):
            ab = app.find("addressbook")
            if ab is None:
                continue
            addr = ab.find("address")
            app_data = {
                "last_name": text(ab, "last-name"),
                "first_name": text(ab, "first-name"),
                "orgname": text(ab, "orgname"),
                "city": text(addr, "city") if addr is not None else None,
                "state": text(addr, "state") if addr is not None else None,
                "country": text(addr, "country") if addr is not None else None,
                "sequence": app.get("sequence"),
                "app_type": app.get("app-type"),
                "authority_category": app.get("applicant-authority-category"),
                "designation": app.get("designation"),
                "residence_country": text(ab.find("residence"), "country") if ab.find("residence") is not None else None,
            }
            d["applicants"].append(app_data)

    # Assignees
    d["assignees"] = []
    assignees_el = bib.find("assignees")
    if assignees_el is not None:
        for idx, asg in enumerate(assignees_el.findall("assignee")):
            ab = asg.find("addressbook")
            if ab is None:
                continue
            addr = ab.find("address")
            asg_data = {
                "last_name": text(ab, "last-name"),
                "first_name": text(ab, "first-name"),
                "orgname": text(ab, "orgname"),
                "city": text(addr, "city") if addr is not None else None,
                "state": text(addr, "state") if addr is not None else None,
                "country": text(addr, "country") if addr is not None else None,
                "role": text(ab, "role"),
                "sequence": idx,
            }
            d["assignees"].append(asg_data)

    # Grant-specific: Examiners
    d["examiners"] = []
    examiners_el = bib.find("examiners")
    if examiners_el is not None:
        primary = examiners_el.find("primary-examiner")
        if primary is not None:
            d["examiners"].append({
                "last_name": text(primary, "last-name"),
                "first_name": text(primary, "first-name"),
                "department": text(primary, "department"),
                "examiner_type": "primary",
            })
        for assistant in examiners_el.findall("assistant-examiner"):
            d["examiners"].append({
                "last_name": text(assistant, "last-name"),
                "first_name": text(assistant, "first-name"),
                "department": None,
                "examiner_type": "assistant",
            })

    # Grant-specific: Agents/Attorneys
    d["agents"] = []
    agents_el = bib.find("us-parties/agents")
    if agents_el is not None:
        for agent in agents_el.findall("agent"):
            ab = agent.find("addressbook")
            if ab is None:
                continue
            addr = ab.find("address")
            agent_data = {
                "last_name": text(ab, "last-name"),
                "first_name": text(ab, "first-name"),
                "orgname": text(ab, "orgname"),
                "city": text(addr, "city") if addr is not None else None,
                "state": text(addr, "state") if addr is not None else None,
                "country": text(addr, "country") if addr is not None else None,
                "rep_type": agent.get("rep-type"),
                "sequence": agent.get("sequence"),
            }
            d["agents"].append(agent_data)

    # Grant-specific: References cited
    d["references_cited"] = _parse_references_cited(bib)

    # Grant-specific: Term of grant
    d["grant_term"] = None
    term_el = bib.find("us-term-of-grant")
    if term_el is not None:
        d["grant_term"] = {
            "length_of_grant": None,
            "term_extension": None,
        }
        log = text(term_el, "length-of-grant")
        if log:
            try:
                d["grant_term"]["length_of_grant"] = int(log)
            except ValueError:
                pass
        ext = text(term_el, "us-term-extension")
        if ext:
            try:
                d["grant_term"]["term_extension"] = int(ext)
            except ValueError:
                d["grant_term"]["term_extension"] = ext

    # Grant-specific: Classification Locarno
    d["classifications_locarno"] = []
    loc_el = bib.find("classification-locarno")
    if loc_el is not None:
        d["classifications_locarno"].append({
            "edition": text(loc_el, "edition"),
            "main_classification": text(loc_el, "main-classification"),
        })

    # Grant-specific: Field of classification search
    d["field_of_classification_search"] = _parse_field_of_classification_search(bib)

    # Grant-specific: PCT publishing data
    d["pct_publishing"] = _parse_pct_publishing(bib)

    # Shared elements
    d["classifications_ipcr"] = _parse_classifications_ipcr(bib)
    d["classifications_cpc"] = _parse_classifications_cpc(bib)
    d["classifications_national"] = _parse_classifications_national(bib)
    d["priority_claims"] = _parse_priority_claims(bib)
    d["pct_filing"] = _parse_pct_filing(bib)
    d["related_documents"] = _parse_related_documents(bib)
    d["botanic"] = _parse_botanic(bib)

    return d


# ============================================================
# Shared sub-parsers
# ============================================================

def _parse_classifications_ipcr(bib):
    results = []
    container = bib.find("classifications-ipcr")
    if container is None:
        return results
    for cl in container.findall("classification-ipcr"):
        data = {
            "ipc_version_date": text(cl.find("ipc-version-indicator"), "date") if cl.find("ipc-version-indicator") is not None else None,
            "classification_level": text(cl, "classification-level"),
            "section": text(cl, "section"),
            "ipc_class": text(cl, "class"),
            "subclass": text(cl, "subclass"),
            "main_group": text(cl, "main-group"),
            "subgroup": text(cl, "subgroup"),
            "symbol_position": text(cl, "symbol-position"),
            "classification_value": text(cl, "classification-value"),
            "action_date": text(cl.find("action-date"), "date") if cl.find("action-date") is not None else None,
            "generating_office_country": text(cl.find("generating-office"), "country") if cl.find("generating-office") is not None else None,
            "classification_status": text(cl, "classification-status"),
            "classification_data_source": text(cl, "classification-data-source"),
        }
        results.append(data)
    return results


def _parse_classifications_cpc(bib):
    results = []
    container = bib.find("classifications-cpc")
    if container is None:
        return results
    # Main CPC
    main = container.find("main-cpc")
    if main is not None:
        for cl in main.findall("classification-cpc"):
            results.append(_parse_cpc_classification(cl, is_main=True))
    # Further CPC
    further = container.find("further-cpc")
    if further is not None:
        for cl in further.findall("classification-cpc"):
            results.append(_parse_cpc_classification(cl, is_main=False))
    return results


def _parse_cpc_classification(cl, is_main=False):
    return {
        "cpc_version_date": text(cl.find("cpc-version-indicator"), "date") if cl.find("cpc-version-indicator") is not None else None,
        "section": text(cl, "section"),
        "cpc_class": text(cl, "class"),
        "subclass": text(cl, "subclass"),
        "main_group": text(cl, "main-group"),
        "subgroup": text(cl, "subgroup"),
        "symbol_position": text(cl, "symbol-position"),
        "classification_value": text(cl, "classification-value"),
        "action_date": text(cl.find("action-date"), "date") if cl.find("action-date") is not None else None,
        "generating_office_country": text(cl.find("generating-office"), "country") if cl.find("generating-office") is not None else None,
        "classification_status": text(cl, "classification-status"),
        "classification_data_source": text(cl, "classification-data-source"),
        "scheme_origination_code": text(cl, "scheme-origination-code"),
        "is_main": is_main,
    }


def _parse_classifications_national(bib):
    results = []
    container = bib.find("classification-national")
    if container is None:
        return results
    data = {
        "country": text(container, "country"),
        "main_classification": text(container, "main-classification"),
        "additional_info": text(container, "additional-info"),
    }
    results.append(data)
    return results


def _parse_priority_claims(bib):
    results = []
    container = bib.find("priority-claims")
    if container is None:
        return results
    for pc in container.findall("priority-claim"):
        data = {
            "sequence": pc.get("sequence"),
            "kind": pc.get("kind"),
            "country": text(pc, "country"),
            "doc_number": text(pc, "doc-number"),
            "date": text(pc, "date"),
        }
        results.append(data)
    return results


def _parse_pct_filing(bib):
    pct_el = bib.find("pct-or-regional-filing-data")
    if pct_el is None:
        return None
    doc_id = pct_el.find("document-id")
    if doc_id is None:
        return None
    d = {
        "country": text(doc_id, "country"),
        "doc_number": text(doc_id, "doc-number"),
        "date": text(doc_id, "date"),
    }
    # 371(c)(12) date
    d371 = pct_el.find("us-371c12-date")
    if d371 is not None:
        d["us_371c12_date"] = text(d371, "date")
    else:
        d["us_371c12_date"] = None
    return d


def _parse_pct_publishing(bib):
    pct_el = bib.find("pct-or-regional-publishing-data")
    if pct_el is None:
        return None
    doc_id = pct_el.find("document-id")
    if doc_id is None:
        return None
    return {
        "country": text(doc_id, "country"),
        "doc_number": text(doc_id, "doc-number"),
        "kind": text(doc_id, "kind"),
        "date": text(doc_id, "date"),
    }


def _parse_related_documents(bib):
    results = []
    container = bib.find("us-related-documents")
    if container is None:
        return results

    # Provisional applications
    for prov in container.findall("us-provisional-application"):
        doc_id = prov.find("document-id")
        if doc_id is not None:
            results.append({
                "relation_type": "us-provisional-application",
                "parent_country": text(doc_id, "country"),
                "parent_doc_number": text(doc_id, "doc-number"),
                "parent_date": text(doc_id, "date"),
                "parent_status": None,
                "parent_grant_doc_number": None,
                "parent_grant_date": None,
                "child_country": None,
                "child_doc_number": None,
            })

    # Continuations, divisions, continuations-in-part
    for rel_type, tag in [
        ("continuation", "continuation"),
        ("division", "division"),
        ("continuation-in-part", "continuation-in-part"),
    ]:
        for rel_container in container.findall(tag):
            rel = rel_container.find("relation")
            if rel is None:
                continue
            rd = {
                "relation_type": rel_type,
                "parent_status": None,
                "parent_grant_doc_number": None,
                "parent_grant_date": None,
                "child_country": None,
                "child_doc_number": None,
            }
            parent = rel.find("parent-doc")
            if parent is not None:
                doc_id = parent.find("document-id")
                if doc_id is not None:
                    rd["parent_country"] = text(doc_id, "country")
                    rd["parent_doc_number"] = text(doc_id, "doc-number")
                    rd["parent_date"] = text(doc_id, "date")
                rd["parent_status"] = text(parent, "parent-status")
                grant_doc = parent.find("parent-grant-document")
                if grant_doc is not None:
                    gd_id = grant_doc.find("document-id")
                    if gd_id is not None:
                        rd["parent_grant_doc_number"] = text(gd_id, "doc-number")
                        rd["parent_grant_date"] = text(gd_id, "date")
            child = rel.find("child-doc")
            if child is not None:
                doc_id = child.find("document-id")
                if doc_id is not None:
                    rd["child_country"] = text(doc_id, "country")
                    rd["child_doc_number"] = text(doc_id, "doc-number")
            results.append(rd)

    # Related publications (grants only)
    for rp in container.findall("related-publication"):
        doc_id = rp.find("document-id")
        if doc_id is not None:
            results.append({
                "relation_type": "related-publication",
                "parent_country": text(doc_id, "country"),
                "parent_doc_number": text(doc_id, "doc-number"),
                "parent_date": text(doc_id, "date"),
                "parent_status": None,
                "parent_grant_doc_number": None,
                "parent_grant_date": None,
                "child_country": None,
                "child_doc_number": None,
            })

    return results


def _parse_references_cited(bib):
    results = []
    container = bib.find("us-references-cited")
    if container is None:
        return results
    for citation in container.findall("us-citation"):
        # Patent citation
        patcit = citation.find("patcit")
        if patcit is not None:
            doc_id = patcit.find("document-id")
            pc = {
                "citation_type": "patent",
                "citation_num": patcit.get("num"),
                "pat_country": text(doc_id, "country") if doc_id is not None else None,
                "pat_doc_number": text(doc_id, "doc-number") if doc_id is not None else None,
                "pat_kind": text(doc_id, "kind") if doc_id is not None else None,
                "pat_name": text(doc_id, "name") if doc_id is not None else None,
                "pat_date": text(doc_id, "date") if doc_id is not None else None,
                "npl_text": None,
                "category": text(citation, "category"),
                "classification_cpc_text": text(citation, "classification-cpc-text"),
            }
            results.append(pc)
            continue
        # NPL citation
        nplcit = citation.find("nplcit")
        if nplcit is not None:
            npl = {
                "citation_type": "npl",
                "citation_num": nplcit.get("num"),
                "pat_country": None,
                "pat_doc_number": None,
                "pat_kind": None,
                "pat_name": None,
                "pat_date": None,
                "npl_text": text(nplcit, "othercit"),
                "category": text(citation, "category"),
                "classification_cpc_text": text(citation, "classification-cpc-text"),
            }
            results.append(npl)
    return results


def _parse_field_of_classification_search(bib):
    results = []
    container = bib.find("us-field-of-classification-search")
    if container is None:
        return results
    for nat in container.findall("classification-national"):
        results.append({
            "search_country": text(nat, "country"),
            "search_main_classification": text(nat, "main-classification"),
            "search_additional_info": text(nat, "additional-info"),
            "search_cpc_text": None,
        })
    for cpc_text in container.findall("classification-cpc-text"):
        results.append({
            "search_country": None,
            "search_main_classification": None,
            "search_additional_info": None,
            "search_cpc_text": cpc_text.text.strip() if cpc_text.text else None,
        })
    return results


def _parse_botanic(bib):
    bot = bib.find("us-botanic")
    if bot is None:
        return None
    return {
        "latin_name": text(bot, "latin-name"),
        "variety": text(bot, "variety"),
    }


# ============================================================
# Database operations
# ============================================================

class DatabaseLoader:
    """Handles inserting parsed records into SQLite with entity dedup."""

    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._person_cache = {}
        self._assignee_cache = {}
        self._examiner_cache = {}
        self._attorney_cache = {}

    def close(self):
        self.conn.close()

    def _get_or_create_person(self, last_name, first_name, suffix, orgname, city, state, country):
        h = compute_entity_hash(last_name or "", first_name or "", orgname or "", city or "", state or "", country or "")
        if h in self._person_cache:
            return self._person_cache[h], False
        cur = self.conn.execute("SELECT id FROM person WHERE entity_hash = ?", (h,))
        row = cur.fetchone()
        if row:
            self._person_cache[h] = row[0]
            return row[0], False
        cur = self.conn.execute(
            "INSERT INTO person (last_name, first_name, suffix, orgname, city, state, country, entity_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (last_name, first_name, suffix, orgname, city, state, country, h),
        )
        pid = cur.lastrowid
        self._person_cache[h] = pid
        return pid, True

    def _get_or_create_assignee(self, last_name, first_name, orgname, city, state, country):
        h = compute_entity_hash(last_name or "", first_name or "", orgname or "", city or "", state or "", country or "")
        if h in self._assignee_cache:
            return self._assignee_cache[h], False
        cur = self.conn.execute("SELECT id FROM assignee WHERE entity_hash = ?", (h,))
        row = cur.fetchone()
        if row:
            self._assignee_cache[h] = row[0]
            return row[0], False
        cur = self.conn.execute(
            "INSERT INTO assignee (last_name, first_name, orgname, city, state, country, entity_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (last_name, first_name, orgname, city, state, country, h),
        )
        aid = cur.lastrowid
        self._assignee_cache[h] = aid
        return aid, True

    def _get_or_create_examiner(self, last_name, first_name, department, examiner_type):
        h = compute_entity_hash(last_name or "", first_name or "", department or "", examiner_type or "")
        if h in self._examiner_cache:
            return self._examiner_cache[h], False
        cur = self.conn.execute("SELECT id FROM examiner WHERE entity_hash = ?", (h,))
        row = cur.fetchone()
        if row:
            self._examiner_cache[h] = row[0]
            return row[0], False
        cur = self.conn.execute(
            "INSERT INTO examiner (last_name, first_name, department, examiner_type, entity_hash) VALUES (?, ?, ?, ?, ?)",
            (last_name, first_name, department, examiner_type, h),
        )
        eid = cur.lastrowid
        self._examiner_cache[h] = eid
        return eid, True

    def _get_or_create_attorney(self, last_name, first_name, orgname, city, state, country, rep_type):
        h = compute_entity_hash(last_name or "", first_name or "", orgname or "", city or "", state or "", country or "")
        if h in self._attorney_cache:
            return self._attorney_cache[h], False
        cur = self.conn.execute("SELECT id FROM attorney_agent_firm WHERE entity_hash = ?", (h,))
        row = cur.fetchone()
        if row:
            self._attorney_cache[h] = row[0]
            return row[0], False
        cur = self.conn.execute(
            "INSERT INTO attorney_agent_firm (last_name, first_name, orgname, city, state, country, rep_type, entity_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (last_name, first_name, orgname, city, state, country, rep_type, h),
        )
        aid = cur.lastrowid
        self._attorney_cache[h] = aid
        return aid, True

    def insert_publication(self, d):
        """Insert a parsed publication dict and all related records."""
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO publication
            (file_reference, date_produced, date_published, dtd_version,
             country, doc_number, kind, pub_date,
             appl_type, appl_country, appl_doc_number, appl_date,
             series_code, invention_title, abstract_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (d.get("file_reference"), d.get("date_produced"), d.get("date_published"),
             d.get("dtd_version"),
             d["country"], d["doc_number"], d["kind"], d["pub_date"],
             d["appl_type"], d.get("appl_country"), d.get("appl_doc_number"), d.get("appl_date"),
             d.get("series_code"), d.get("invention_title"), d.get("abstract_text")),
        )
        if cur.rowcount == 0:
            # Duplicate — get existing ID
            row = self.conn.execute(
                "SELECT id FROM publication WHERE country=? AND doc_number=? AND kind=? AND pub_date=?",
                (d["country"], d["doc_number"], d["kind"], d["pub_date"]),
            ).fetchone()
            if row is None:
                return None
            return row[0]

        pub_id = cur.lastrowid

        # Inventors
        for inv in d.get("inventors", []):
            pid, _ = self._get_or_create_person(
                inv["last_name"], inv["first_name"], inv.get("suffix"), inv.get("orgname"),
                inv["city"], inv["state"], inv["country"],
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO publication_inventor (publication_id, person_id, sequence, designation) VALUES (?, ?, ?, ?)",
                (pub_id, pid, inv.get("sequence"), inv.get("designation")),
            )

        # Applicants
        for app in d.get("applicants", []):
            pid, _ = self._get_or_create_person(
                app["last_name"], app["first_name"], None, app.get("orgname"),
                app["city"], app["state"], app["country"],
            )
            self.conn.execute(
                """INSERT OR IGNORE INTO publication_applicant
                (publication_id, person_id, sequence, app_type, authority_category, designation, residence_country)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (pub_id, pid, app.get("sequence"), app.get("app_type"),
                 app.get("authority_category"), app.get("designation"), app.get("residence_country")),
            )

        # Assignees
        for asg in d.get("assignees", []):
            aid, _ = self._get_or_create_assignee(
                asg["last_name"], asg["first_name"], asg.get("orgname"),
                asg["city"], asg["state"], asg["country"],
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO publication_assignee (publication_id, assignee_id, role, sequence) VALUES (?, ?, ?, ?)",
                (pub_id, aid, asg.get("role"), asg.get("sequence")),
            )

        # Classifications
        self._insert_classifications("publication", pub_id, d)

        # Priority claims
        self._insert_priority_claims("publication", pub_id, d)

        # PCT filing
        if d.get("pct_filing"):
            pf = d["pct_filing"]
            self.conn.execute(
                """INSERT INTO pct_filing_data (source_type, source_id, country, doc_number, date, us_371c12_date)
                VALUES (?, ?, ?, ?, ?, ?)""",
                ("publication", pub_id, pf["country"], pf["doc_number"], pf["date"], pf.get("us_371c12_date")),
            )

        # Related documents
        self._insert_related_documents("publication", pub_id, d)

        # Botanic
        if d.get("botanic"):
            bot = d["botanic"]
            self.conn.execute(
                "INSERT INTO botanic (source_type, source_id, latin_name, variety) VALUES (?, ?, ?, ?)",
                ("publication", pub_id, bot["latin_name"], bot["variety"]),
            )

        return pub_id

    def insert_grant(self, d):
        """Insert a parsed grant dict and all related records."""
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO grant
            (file_reference, date_produced, date_published, dtd_version,
             country, doc_number, kind, pub_date,
             appl_type, appl_country, appl_doc_number, appl_date,
             series_code, invention_title,
             number_of_claims, exemplary_claim,
             number_of_drawing_sheets, number_of_figures,
             abstract_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (d.get("file_reference"), d.get("date_produced"), d.get("date_published"),
             d.get("dtd_version"),
             d["country"], d["doc_number"], d["kind"], d["pub_date"],
             d["appl_type"], d.get("appl_country"), d.get("appl_doc_number"), d.get("appl_date"),
             d.get("series_code"), d.get("invention_title"),
             d.get("number_of_claims"), d.get("exemplary_claim"),
             d.get("number_of_drawing_sheets"), d.get("number_of_figures"),
             d.get("abstract_text")),
        )
        if cur.rowcount == 0:
            row = self.conn.execute(
                "SELECT id FROM grant WHERE country=? AND doc_number=? AND kind=? AND pub_date=?",
                (d["country"], d["doc_number"], d["kind"], d["pub_date"]),
            ).fetchone()
            if row is None:
                return None
            return row[0]

        grant_id = cur.lastrowid

        # Inventors
        for inv in d.get("inventors", []):
            pid, _ = self._get_or_create_person(
                inv["last_name"], inv["first_name"], inv.get("suffix"), inv.get("orgname"),
                inv["city"], inv["state"], inv["country"],
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO grant_inventor (grant_id, person_id, sequence, designation) VALUES (?, ?, ?, ?)",
                (grant_id, pid, inv.get("sequence"), inv.get("designation")),
            )

        # Applicants
        for app in d.get("applicants", []):
            pid, _ = self._get_or_create_person(
                app["last_name"], app["first_name"], None, app.get("orgname"),
                app["city"], app["state"], app["country"],
            )
            self.conn.execute(
                """INSERT OR IGNORE INTO grant_applicant
                (grant_id, person_id, sequence, app_type, authority_category, designation, residence_country)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (grant_id, pid, app.get("sequence"), app.get("app_type"),
                 app.get("authority_category"), app.get("designation"), app.get("residence_country")),
            )

        # Assignees
        for asg in d.get("assignees", []):
            aid, _ = self._get_or_create_assignee(
                asg["last_name"], asg["first_name"], asg.get("orgname"),
                asg["city"], asg["state"], asg["country"],
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO grant_assignee (grant_id, assignee_id, role, sequence) VALUES (?, ?, ?, ?)",
                (grant_id, aid, asg.get("role"), asg.get("sequence")),
            )

        # Examiners
        for exam in d.get("examiners", []):
            eid, _ = self._get_or_create_examiner(
                exam["last_name"], exam["first_name"], exam.get("department"), exam["examiner_type"],
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO grant_examiner (grant_id, examiner_id, examiner_type) VALUES (?, ?, ?)",
                (grant_id, eid, exam["examiner_type"]),
            )

        # Agents/Attorneys
        for agent in d.get("agents", []):
            aid, _ = self._get_or_create_attorney(
                agent["last_name"], agent["first_name"], agent.get("orgname"),
                agent["city"], agent["state"], agent["country"], agent.get("rep_type"),
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO grant_attorney_agent (grant_id, attorney_agent_id, sequence) VALUES (?, ?, ?)",
                (grant_id, aid, agent.get("sequence")),
            )

        # References cited
        for ref in d.get("references_cited", []):
            self.conn.execute(
                """INSERT INTO reference_cited
                (grant_id, citation_num, citation_type,
                 pat_country, pat_doc_number, pat_kind, pat_name, pat_date,
                 npl_text, category, classification_cpc_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (grant_id, ref.get("citation_num"), ref["citation_type"],
                 ref.get("pat_country"), ref.get("pat_doc_number"),
                 ref.get("pat_kind"), ref.get("pat_name"), ref.get("pat_date"),
                 ref.get("npl_text"), ref.get("category"), ref.get("classification_cpc_text")),
            )

        # Grant term
        if d.get("grant_term"):
            gt = d["grant_term"]
            self.conn.execute(
                "INSERT INTO grant_term (grant_id, length_of_grant, term_disclaimer) VALUES (?, ?, ?)",
                (grant_id, gt.get("length_of_grant"), gt.get("term_extension")),
            )

        # Locarno classifications
        for loc in d.get("classifications_locarno", []):
            self.conn.execute(
                "INSERT INTO classification_locarno (grant_id, edition, main_classification) VALUES (?, ?, ?)",
                (grant_id, loc["edition"], loc["main_classification"]),
            )

        # Field of classification search
        for fcs in d.get("field_of_classification_search", []):
            self.conn.execute(
                """INSERT INTO field_of_classification_search
                (grant_id, search_country, search_main_classification, search_additional_info, search_cpc_text)
                VALUES (?, ?, ?, ?, ?)""",
                (grant_id, fcs.get("search_country"), fcs.get("search_main_classification"),
                 fcs.get("search_additional_info"), fcs.get("search_cpc_text")),
            )

        # PCT publishing data
        if d.get("pct_publishing"):
            pp = d["pct_publishing"]
            self.conn.execute(
                """INSERT INTO pct_publishing_data (source_type, source_id, country, doc_number, kind, date)
                VALUES (?, ?, ?, ?, ?, ?)""",
                ("grant", grant_id, pp["country"], pp["doc_number"], pp["kind"], pp["date"]),
            )

        # Classifications (shared)
        self._insert_classifications("grant", grant_id, d)

        # Priority claims
        self._insert_priority_claims("grant", grant_id, d)

        # PCT filing
        if d.get("pct_filing"):
            pf = d["pct_filing"]
            self.conn.execute(
                """INSERT INTO pct_filing_data (source_type, source_id, country, doc_number, date, us_371c12_date)
                VALUES (?, ?, ?, ?, ?, ?)""",
                ("grant", grant_id, pf["country"], pf["doc_number"], pf["date"], pf.get("us_371c12_date")),
            )

        # Related documents
        self._insert_related_documents("grant", grant_id, d)

        # Botanic
        if d.get("botanic"):
            bot = d["botanic"]
            self.conn.execute(
                "INSERT INTO botanic (source_type, source_id, latin_name, variety) VALUES (?, ?, ?, ?)",
                ("grant", grant_id, bot["latin_name"], bot["variety"]),
            )

        return grant_id

    def _insert_classifications(self, source_type, source_id, d):
        for ipc in d.get("classifications_ipcr", []):
            self.conn.execute(
                """INSERT INTO classification_ipcr
                (source_type, source_id, ipc_version_date, classification_level,
                 section, ipc_class, subclass, main_group, subgroup,
                 symbol_position, classification_value, action_date,
                 generating_office_country, classification_status, classification_data_source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (source_type, source_id,
                 ipc.get("ipc_version_date"), ipc.get("classification_level"),
                 ipc.get("section"), ipc.get("ipc_class"), ipc.get("subclass"),
                 ipc.get("main_group"), ipc.get("subgroup"),
                 ipc.get("symbol_position"), ipc.get("classification_value"),
                 ipc.get("action_date"), ipc.get("generating_office_country"),
                 ipc.get("classification_status"), ipc.get("classification_data_source")),
            )
        for cpc in d.get("classifications_cpc", []):
            self.conn.execute(
                """INSERT INTO classification_cpc
                (source_type, source_id, cpc_version_date,
                 section, cpc_class, subclass, main_group, subgroup,
                 symbol_position, classification_value, action_date,
                 generating_office_country, classification_status, classification_data_source,
                 scheme_origination_code, is_main)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (source_type, source_id,
                 cpc.get("cpc_version_date"),
                 cpc.get("section"), cpc.get("cpc_class"), cpc.get("subclass"),
                 cpc.get("main_group"), cpc.get("subgroup"),
                 cpc.get("symbol_position"), cpc.get("classification_value"),
                 cpc.get("action_date"), cpc.get("generating_office_country"),
                 cpc.get("classification_status"), cpc.get("classification_data_source"),
                 cpc.get("scheme_origination_code"), 1 if cpc.get("is_main") else 0),
            )
        for nat in d.get("classifications_national", []):
            self.conn.execute(
                """INSERT INTO classification_national
                (source_type, source_id, country, main_classification, additional_info)
                VALUES (?, ?, ?, ?, ?)""",
                (source_type, source_id,
                 nat.get("country"), nat.get("main_classification"), nat.get("additional_info")),
            )

    def _insert_priority_claims(self, source_type, source_id, d):
        for pc in d.get("priority_claims", []):
            self.conn.execute(
                """INSERT INTO priority_claim
                (source_type, source_id, sequence, kind, country, doc_number, date)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (source_type, source_id, pc.get("sequence"), pc.get("kind"),
                 pc.get("country"), pc.get("doc_number"), pc.get("date")),
            )

    def _insert_related_documents(self, source_type, source_id, d):
        for rd in d.get("related_documents", []):
            self.conn.execute(
                """INSERT INTO related_document
                (source_type, source_id, relation_type,
                 parent_country, parent_doc_number, parent_date, parent_status,
                 parent_grant_doc_number, parent_grant_date,
                 child_country, child_doc_number)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (source_type, source_id, rd["relation_type"],
                 rd.get("parent_country"), rd.get("parent_doc_number"),
                 rd.get("parent_date"), rd.get("parent_status"),
                 rd.get("parent_grant_doc_number"), rd.get("parent_grant_date"),
                 rd.get("child_country"), rd.get("child_doc_number")),
            )

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()


# ============================================================
# Main processing logic
# ============================================================

def process_file(filepath, db_path, dataset, delete_source=False):
    """Process a single XML file: split, parse, insert into database."""
    from init_db import init_db

    # Ensure database exists
    if not os.path.exists(db_path):
        init_db(db_path)

    loader = DatabaseLoader(db_path)
    filename = os.path.basename(filepath)

    # Check if already processed
    row = loader.conn.execute(
        "SELECT id FROM processed_file WHERE filename = ?", (filename,)
    ).fetchone()
    if row:
        logging.info("Skipping already-processed file: %s", filename)
        loader.close()
        return True

    # Compute SHA256
    sha256 = hashlib.sha256(open(filepath, "rb").read()).hexdigest()

    # Split and parse
    records = split_xml_records(filepath)
    logging.info("File %s: %d records found", filename, len(records))

    success_count = 0
    failure_count = 0

    try:
        for i, record_bytes in enumerate(records):
            try:
                root = parse_record(record_bytes)
            except Exception as e:
                logging.error("Failed to parse record %d in %s: %s", i, filename, e)
                failure_count += 1
                continue

            if dataset == "publication":
                d = parse_publication(root)
                if d:
                    pid = loader.insert_publication(d)
                    if pid:
                        success_count += 1
                    else:
                        logging.warning("Duplicate publication in record %d of %s", i, filename)
                        failure_count += 1
            elif dataset == "grant":
                d = parse_grant(root)
                if d:
                    gid = loader.insert_grant(d)
                    if gid:
                        success_count += 1
                    else:
                        logging.warning("Duplicate grant in record %d of %s", i, filename)
                        failure_count += 1
            else:
                logging.error("Unknown dataset: %s", dataset)
                loader.rollback()
                loader.close()
                return False

        # Record in processed_file
        # Extract date from filename like ipab20260122_wk04.xml
        date_match = re.search(r"(\d{4})(\d{2})(\d{2})", filename)
        file_date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}" if date_match else None
        week_match = re.search(r"_wk(\d+)", filename)
        week_number = int(week_match.group(1)) if week_match else None

        loader.conn.execute(
            """INSERT INTO processed_file
            (filename, dataset, file_date, week_number, record_count, processed_at, sha256)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (filename, dataset, file_date, week_number, success_count,
             datetime.now().isoformat(), sha256),
        )
        loader.commit()

        logging.info("File %s: %d succeeded, %d failed", filename, success_count, failure_count)

        # Delete source data if requested
        if delete_source and failure_count == 0:
            os.remove(filepath)
            # Also try to remove the zip if it exists
            zip_name = filename.replace(".xml", ".zip")
            # Check common locations
            for d in ["downloads/publication", "downloads/grant", "extracted/publication", "extracted/grant"]:
                zip_path = os.path.join(os.path.dirname(db_path), d, zip_name)
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                    logging.info("Deleted source zip: %s", zip_path)
            logging.info("Deleted source XML: %s", filepath)

        loader.close()
        return failure_count == 0

    except Exception as e:
        logging.error("Fatal error processing %s: %s", filename, e)
        loader.rollback()
        loader.close()
        return False


def main():
    parser = argparse.ArgumentParser(description="Process USPTO bibliographic XML into SQLite")
    parser.add_argument("--dataset", required=True, choices=["publication", "grant"],
                        help="Dataset type to process")
    parser.add_argument("--input-dir", default="extracted",
                        help="Base directory for extracted XML files (default: %(default)s)")
    parser.add_argument("--db", default="bibliographic_data.db",
                        help="Path to SQLite database (default: %(default)s)")
    parser.add_argument("--delete-source-data", "-d", action="store_true",
                        help="Delete source XML and zip files after successful processing")
    parser.add_argument("--file", nargs="*", help="Process only these specific XML files")
    parser.add_argument("--log-level", default="INFO", help="Log level (default: %(default)s)")
    args = parser.parse_args()

    setup_logging(level=getattr(logging, args.log_level.upper()))

    input_dir = os.path.join(args.input_dir, args.dataset)
    if not os.path.isdir(input_dir):
        logging.error("Input directory does not exist: %s", input_dir)
        sys.exit(1)

    if args.file:
        files = args.file
    else:
        # Find unprocessed XML files
        loader = DatabaseLoader(args.db)
        processed = set(
            row[0] for row in loader.conn.execute("SELECT filename FROM processed_file WHERE dataset=?", (args.dataset,)).fetchall()
        )
        loader.close()
        files = sorted(
            f for f in os.listdir(input_dir)
            if f.endswith(".xml") and f not in processed
        )

    if not files:
        logging.info("No files to process")
        return

    total = len(files)
    ok = 0
    for i, fname in enumerate(files, 1):
        fpath = os.path.join(input_dir, fname)
        logging.info("Processing [%d/%d]: %s", i, total, fname)
        if process_file(fpath, args.db, args.dataset, delete_source=args.delete_source_data):
            ok += 1

    logging.info("Done: %d/%d files processed successfully", ok, total)


if __name__ == "__main__":
    main()