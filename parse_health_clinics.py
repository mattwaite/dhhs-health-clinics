#!/usr/bin/env python3
"""
Extract Nebraska DHHS licensed health clinic facility roster from PDF to CSV.
Source: https://dhhs.ne.gov/licensure/Documents/HC_ASC_ESRD%20Lic%20Roster.pdf
"""

import csv
import re
from datetime import date
from pathlib import Path

import pdfplumber
import requests

PDF_URL = "https://dhhs.ne.gov/licensure/Documents/HC_ASC_ESRD%20Lic%20Roster.pdf"
PDF_DIR = Path("pdfs")
DATA_DIR = Path("data")
SLUG = "health_clinics"

SKIP_PAGES = 2   # cover + summary count page
HEADER_LINES = 7  # repeated column-label block at top of every data page

# Record boundary: CITY (County) ZIPCODE CCN SERVICETYPE
# CCN is either NONE, a 28C-prefixed ASC number, or a 6-digit ESRD number
# City character class includes apostrophe for names like O' NEILL
CITY_RE = re.compile(
    r"^([A-Z][A-Za-z\s']+?)\s+\(([A-Za-z\s]+)\)\s+(\d{5})\s+(NONE|28C\d+|\d+)\s*(.*)$"
)

# License number right-justified on the name line: ASC###, ESRD###, HC###
# Not anchored at $ — some records have a spurious service-type word after the license number
# that bleeds in from an adjacent PDF column. We take everything before the license as the name.
LICENSE_RE = re.compile(r'\s+((?:ASC|ESRD|HC)\d+)\b')

# Accreditation right-justified on the address (or name-wrap) line
# Includes TJC (The Joint Commission) and NDAC in addition to AAAHC/ACHC
ACCRED_RE = re.compile(
    r'\s+(NONE|AAAHC(?:[,\s]+ACHC)?|ACHC|TJC|JCAHO|NDAC|CARF|HFAP|DNV)\s*$',
    re.IGNORECASE
)

# Spurious service-type words that bleed from the right PDF column onto address lines
# Matches full words and truncated forms (e.g. HEMODIALYS, HEMOD)
SERVICE_SUFFIX_RE = re.compile(
    r'\s+(?:HOME\s+)?HEMOD\w*\s*$',
    re.IGNORECASE
)

PHONE_RE = re.compile(
    r'TEL:\s*(\(\d{3}\)\s*[\d\-]+)(?:\s+FAX:\s*(\(\d{3}\)\s*[\d\-]+))?'
)

FIELDS = [
    'city', 'county', 'zip_code', 'ccn', 'service_type',
    'facility_name', 'license_no', 'address', 'accreditation',
    'phone', 'fax', 'licensee', 'administrator',
    'administration_address', 'branches', 'date_parsed',
]


def download_pdf(url: str = PDF_URL) -> Path:
    PDF_DIR.mkdir(exist_ok=True)
    date_str = date.today().strftime("%Y-%m-%d")
    dest = PDF_DIR / f"{SLUG}_{date_str}.pdf"
    if dest.exists():
        print(f"Already downloaded: {dest}")
        return dest
    print(f"Downloading {url} ...")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    dest.write_bytes(r.content)
    print(f"Saved: {dest}")
    return dest


def looks_like_address(text: str) -> bool:
    """Heuristic: does this text look like a street address rather than a name fragment?"""
    return bool(re.match(r'^\d+\b|^P\.?\s*O\.?\s*\b|^ROUTE\s', text.strip(), re.I))


def _blank_record(m: re.Match, date_str: str) -> dict:
    return {
        'city': m.group(1).strip(),
        'county': m.group(2).strip(),
        'zip_code': m.group(3),
        'ccn': m.group(4),
        'service_type': m.group(5).strip(),
        'facility_name': '',
        'license_no': '',
        'address': '',
        'accreditation': '',
        'phone': '',
        'fax': '',
        'licensee': '',
        'administrator': '',
        'administration_address': '',
        'branches': '',
        'date_parsed': date_str,
    }


def _collect_lines(pdf_path: Path) -> list[str]:
    """Pull text from all data pages, stripping page headers."""
    lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            if page_num < SKIP_PAGES:
                continue
            text = page.extract_text()
            if not text:
                continue
            for line in text.split('\n')[HEADER_LINES:]:
                line = line.strip()
                if line:
                    lines.append(line)
    return lines


def extract_records(pdf_path: Path, date_str: str = None) -> list[dict]:
    date_str = date_str or date.today().isoformat()
    lines = _collect_lines(pdf_path)

    records = []
    current = None
    state = 'name'
    co_pending = False  # True when a c/o line may continue on the next line

    for line in lines:
        if line.startswith('TOTAL FACILITIES'):
            if current:
                records.append(current)
                current = None
            break

        # New record boundary — always checked first
        m = CITY_RE.match(line)
        if m:
            if current:
                records.append(current)
            current = _blank_record(m, date_str)
            state = 'name'
            co_pending = False
            continue

        if current is None:
            continue

        # c/o address continuation (before BRANCH check so wrapping works correctly)
        if co_pending and not line.startswith('BRANCH:'):
            current['administration_address'] += ' ' + line
            continue
        co_pending = False

        # Optional branch location lines
        if line.startswith('BRANCH:'):
            branch = line[7:].strip()
            sep = '; ' if current['branches'] else ''
            current['branches'] += sep + branch
            continue

        # Per-field state machine
        if state == 'name':
            m = LICENSE_RE.search(line)
            if m:
                current['license_no'] = m.group(1)
                current['facility_name'] = line[:m.start()].strip()
            else:
                current['facility_name'] = line
            state = 'address'

        elif state == 'address':
            # Strip spurious HEMODIALYSIS suffix before looking for accreditation
            line = SERVICE_SUFFIX_RE.sub('', line).strip()
            m = ACCRED_RE.search(line)
            left = line[:m.start()].strip() if m else line.strip()
            accred = m.group(1).strip() if m else ''

            # Accreditation always appears on whichever line holds it; don't overwrite
            if accred and not current['accreditation']:
                current['accreditation'] = accred

            if not current['address']:
                if looks_like_address(left):
                    # This line is the street address
                    current['address'] = left
                    state = 'phone'
                elif left:
                    # Long facility name wrapped onto a second line; address follows next
                    current['facility_name'] += ' ' + left

        elif state == 'phone':
            m = PHONE_RE.search(line)
            if m:
                current['phone'] = m.group(1)
                current['fax'] = m.group(2) or ''
                state = 'licensee'

        elif state == 'licensee':
            current['licensee'] = line
            state = 'admin'

        elif state == 'admin':
            current['administrator'] = line
            state = 'co'

        elif state == 'co':
            if line.startswith('c/o:'):
                current['administration_address'] = line[4:].strip()
                co_pending = True
                state = 'done'

    if current:
        records.append(current)

    return records


def save_to_csv(records: list[dict], output_path: Path = None) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    if output_path is None:
        date_str = date.today().strftime("%Y-%m-%d")
        output_path = DATA_DIR / f"{SLUG}_{date_str}.csv"
    if not records:
        print("No records to write.")
        return output_path
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)
    print(f"Wrote {len(records)} records to {output_path}")
    return output_path


def main():
    pdf_path = download_pdf()
    date_str = date.today().strftime("%Y-%m-%d")
    records = extract_records(pdf_path, date_str=date_str)
    print(f"Extracted {len(records)} records (expected 108)")

    if records:
        print("\nSample — first 3 records:")
        for rec in records[:3]:
            for k, v in rec.items():
                if v:
                    print(f"  {k}: {v}")
            print()

    save_to_csv(records)


if __name__ == '__main__':
    main()
