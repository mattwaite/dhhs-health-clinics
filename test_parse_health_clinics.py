"""
Tests for parse_health_clinics.py
Run: pytest test_parse_health_clinics.py -v
"""

import csv
import re
from pathlib import Path

import pytest

from parse_health_clinics import extract_records, save_to_csv

PDF_PATH = next(Path("pdfs").glob("*.pdf"), None)


@pytest.fixture(scope="module")
def records():
    assert PDF_PATH is not None, "No PDF found in pdfs/ — run parse_health_clinics.py first"
    date_str = PDF_PATH.stem.split("_")[-1]
    return extract_records(PDF_PATH, date_str)


@pytest.fixture(scope="module")
def csv_path(records, tmp_path_factory):
    out = tmp_path_factory.mktemp("data") / "test_output.csv"
    save_to_csv(records, out)
    return out


class TestRecordCount:
    """Verify total record count matches the PDF footer (108 as of 2026-04-15)."""

    EXPECTED_MIN = 103   # 108 − 5%
    EXPECTED_MAX = 113   # 108 + 5%

    def test_record_count_in_range(self, records):
        count = len(records)
        assert self.EXPECTED_MIN <= count <= self.EXPECTED_MAX, (
            f"Expected {self.EXPECTED_MIN}–{self.EXPECTED_MAX} records, got {count}"
        )

    def test_no_duplicate_license_numbers(self, records):
        license_nos = [r["license_no"] for r in records if r.get("license_no")]
        assert len(license_nos) == len(set(license_nos)), (
            "Duplicate license numbers found — each facility should appear once"
        )


class TestRequiredColumns:
    """Verify critical columns are filled at acceptable rates."""

    # All fields except fax (66%) and branches (7%) are 100% in the current PDF
    FILL_RATE_THRESHOLDS = {
        "city": 1.00,
        "county": 1.00,
        "zip_code": 1.00,
        "ccn": 1.00,
        "service_type": 1.00,
        "facility_name": 1.00,
        "license_no": 1.00,
        "address": 1.00,
        "accreditation": 1.00,
        "phone": 1.00,
        "fax": 0.60,           # Many dialysis/HC facilities omit fax
        "licensee": 1.00,
        "administrator": 1.00,
        "administration_address": 1.00,
        "date_parsed": 1.00,
    }

    @pytest.mark.parametrize("field,threshold", FILL_RATE_THRESHOLDS.items())
    def test_fill_rate(self, records, field, threshold):
        total = len(records)
        filled = sum(1 for r in records if r.get(field, "").strip())
        rate = filled / total
        assert rate >= threshold, (
            f"Field '{field}' fill rate {rate:.1%} is below threshold {threshold:.0%} "
            f"({filled}/{total} records)"
        )


class TestDataFormats:
    """Verify field values conform to expected formats."""

    LICENSE_RE = re.compile(r"^(ASC|ESRD|HC)\d{3}$")
    ASC_CCN_RE = re.compile(r"^28C\d{7}$")
    ESRD_CCN_RE = re.compile(r"^\d{6}$")
    PHONE_RE = re.compile(r"^\(\d{3}\) \d{3}-\d{4}$")
    ZIP_RE = re.compile(r"^\d{5}$")
    DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    KNOWN_SERVICE_TYPES = {
        "AMBULATORY SURGICAL CENTER",
        "HEMODIALYSIS",
        "HOME HEMODIALYSIS",
        "HOME PERITONEAL DIALYSIS",
        "PUBLIC HEALTH CLINIC",
        "NONE",
    }
    KNOWN_ACCREDITATIONS = {"NONE", "AAAHC", "ACHC", "AAAHC, ACHC", "TJC", "JCAHO", "NDAC", "CARF", "HFAP", "DNV"}

    def test_license_numbers_match_pattern(self, records):
        bad = [r["license_no"] for r in records if not self.LICENSE_RE.match(r["license_no"])]
        assert not bad, f"Unexpected license_no formats: {bad[:5]}"

    def test_asc_ccn_format(self, records):
        """ASC facilities have CCNs starting with 28C followed by 7 digits."""
        asc = [r for r in records if r["service_type"] == "AMBULATORY SURGICAL CENTER" and r["ccn"] != "NONE"]
        bad = [r["ccn"] for r in asc if not self.ASC_CCN_RE.match(r["ccn"])]
        assert not bad, f"Malformed ASC CCN values: {bad[:5]}"

    def test_esrd_ccn_format(self, records):
        """ESRD/dialysis facilities have 6-digit numeric CCNs."""
        dialysis = [r for r in records if "HEMODIALYSIS" in r["service_type"] or "DIALYSIS" in r["service_type"]]
        bad = [r["ccn"] for r in dialysis if r["ccn"] != "NONE" and not self.ESRD_CCN_RE.match(r["ccn"])]
        assert not bad, f"Malformed ESRD CCN values: {bad[:5]}"

    def test_phone_numbers_are_formatted(self, records):
        bad = [r["phone"] for r in records if r.get("phone") and not self.PHONE_RE.match(r["phone"])]
        assert len(bad) / len(records) < 0.05, (
            f"Too many malformed phone numbers ({len(bad)}): {bad[:5]}"
        )

    def test_zip_codes_are_5_digits(self, records):
        bad = [r["zip_code"] for r in records if not self.ZIP_RE.match(r["zip_code"])]
        assert not bad, f"Invalid zip codes: {bad}"

    def test_all_nebraska_zips(self, records):
        """All facilities should be in Nebraska ZIP code ranges."""
        # Nebraska ZIPs run roughly 680xx–693xx
        bad = [r["zip_code"] for r in records
               if not (68000 <= int(r["zip_code"]) <= 69400)]
        assert not bad, f"ZIP codes outside Nebraska range: {bad}"

    def test_service_types_are_known(self, records):
        unknown = {r["service_type"] for r in records} - self.KNOWN_SERVICE_TYPES
        assert not unknown, f"Unrecognized service_type values: {unknown}"

    def test_accreditations_are_known(self, records):
        unknown = {r["accreditation"].upper() for r in records} - {a.upper() for a in self.KNOWN_ACCREDITATIONS}
        assert not unknown, f"Unrecognized accreditation values: {unknown}"

    def test_date_parsed_format(self, records):
        bad = [r["date_parsed"] for r in records if not self.DATE_RE.match(r["date_parsed"])]
        assert not bad, f"Invalid date_parsed formats: {bad[:5]}"

    def test_license_prefix_matches_service_type(self, records):
        """ASC licenses start with ASC, ESRD with ESRD, health clinic with HC."""
        for r in records:
            lic = r["license_no"]
            svc = r["service_type"]
            if "AMBULATORY" in svc:
                assert lic.startswith("ASC"), f"ASC facility has non-ASC license: {lic} ({r['facility_name']})"
            elif "HEMODIALYSIS" in svc or "DIALYSIS" in svc:
                assert lic.startswith("ESRD"), f"Dialysis facility has non-ESRD license: {lic} ({r['facility_name']})"
            else:
                assert lic.startswith("HC"), f"Health clinic has non-HC license: {lic} ({r['facility_name']})"


class TestCSVOutput:
    """Verify the CSV file is well-formed."""

    EXPECTED_COLUMNS = [
        "city", "county", "zip_code", "ccn", "service_type",
        "facility_name", "license_no", "address", "accreditation",
        "phone", "fax", "licensee", "administrator",
        "administration_address", "branches", "date_parsed",
    ]

    def test_csv_exists(self, csv_path):
        assert csv_path.exists()
        assert csv_path.stat().st_size > 0

    def test_csv_has_expected_columns(self, csv_path):
        with open(csv_path, newline="", encoding="utf-8") as f:
            actual = csv.DictReader(f).fieldnames
        assert actual == self.EXPECTED_COLUMNS, (
            f"Column mismatch.\nExpected: {self.EXPECTED_COLUMNS}\nActual:   {actual}"
        )

    def test_csv_row_count_matches_records(self, records, csv_path):
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == len(records)

    def test_no_empty_rows(self, csv_path):
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        empty = [i for i, r in enumerate(rows, 1) if not any(r.values())]
        assert not empty, f"Empty rows at CSV lines: {empty}"


class TestKnownRecords:
    """Spot-check specific stable records to catch parsing regression."""

    def test_dialysis_clinic_omaha_present(self, records):
        """DIALYSIS CLINIC, INC. (ESRD008) is a long-standing Omaha dialysis center."""
        match = [r for r in records if r.get("license_no") == "ESRD008"]
        assert match, "ESRD008 (Dialysis Clinic Omaha) not found — possible parsing regression"
        r = match[0]
        assert r["city"].upper() == "OMAHA"
        assert r["ccn"] == "282504"
        assert r["service_type"] == "HEMODIALYSIS"

    def test_oneill_record_present(self, records):
        """O' NEILL (HOLT county) tests the apostrophe-in-city-name edge case."""
        match = [r for r in records if "NEILL" in r.get("city", "").upper()]
        assert match, "O'Neill record not found — city apostrophe regex may have regressed"
        r = match[0]
        assert r["license_no"] == "ESRD028"
        assert r["county"].upper() == "HOLT"

    def test_lincoln_lancaster_health_dept(self, records):
        """Lincoln-Lancaster County Health Department (HC035) is a permanent public entity."""
        match = [r for r in records if r.get("license_no") == "HC035"]
        assert match, "HC035 (Lincoln-Lancaster Health Dept) not found"
        r = match[0]
        assert r["service_type"] == "PUBLIC HEALTH CLINIC"
        assert r["city"].upper() == "LINCOLN"

    def test_wrapped_name_record_parsed_correctly(self, records):
        """SURGICENTER OF NORFOLK has a long dba name that wraps across two PDF lines."""
        match = [r for r in records if r.get("license_no") == "ASC085"]
        assert match, "ASC085 (Surgicenter of Norfolk) not found"
        r = match[0]
        assert "FOUNTAIN POINT" in r["facility_name"].upper(), (
            f"Wrapped name not fully captured: {r['facility_name']}"
        )
        assert r["accreditation"] in ("AAAHC, ACHC", "AAAHC ACHC", "ACHC", "AAAHC"), (
            f"Unexpected accreditation for ASC085: {r['accreditation']}"
        )

    def test_branch_locations_captured(self, records):
        """WCHR / Western Community Health Resources (HC068) has 3 branch locations."""
        match = [r for r in records if r.get("license_no") == "HC068"]
        assert match, "HC068 (WCHR) not found"
        r = match[0]
        assert r["branches"], "HC068 branch locations are empty"
        assert r["branches"].count(";") >= 2, (
            f"Expected at least 3 branch locations, got: {r['branches']}"
        )
