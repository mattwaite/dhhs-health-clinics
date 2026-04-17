# Nebraska DHHS Health Clinic Facility Roster

## Purpose
Extract the Nebraska DHHS licensed health clinic facility roster (108 facilities across three types: ASC, ESRD, HC) from PDF to structured CSV.

## Source PDF
https://dhhs.ne.gov/licensure/Documents/HC_ASC_ESRD%20Lic%20Roster.pdf
Saved to: `pdfs/health_clinics_YYYY-MM-DD.pdf`

## Running
```bash
python parse_health_clinics.py
```

## Testing
```bash
pytest test_parse_health_clinics.py -v
```

## Output
CSV written to: `data/health_clinics_YYYY-MM-DD.csv`
Expected record count: 108 facilities

## Key Implementation Notes
- PDF type: Type A Roster — multi-line block per facility (7–10 lines per record)
- Pages 1–2 are cover/summary — skip them; data starts on page 3
- Each page has a 7-line column-label block to skip
- Record boundary regex: `^([A-Z][A-Za-z\s']+?)\s+\(([A-Za-z\s]+)\)\s+(\d{5})\s+(NONE|28C\d+|\d+)\s*(.*)$`
  - City names can contain apostrophes (e.g., O' NEILL)
- State machine: name → address → phone → licensee → admin → c/o → done
- Facility names can wrap to a second line (long `dba` names) — handled in address state
- `c/o:` address can wrap to the next line — `co_pending` flag tracks continuation
- Optional `BRANCH:` lines follow the c/o line (0–4 per record)
- FAX field may be empty even though the `FAX:` token is present
- LICENSE_RE is NOT end-anchored — some records have spurious service-type words
  (HEMODIALYSIS, HEMOD, HOME HEMODIALYSIS) bleeding from the right PDF column after the license number
- SERVICE_SUFFIX_RE strips those spurious words from address lines before ACCRED_RE runs
- Accreditations seen: NONE, AAAHC, ACHC, AAAHC+ACHC, TJC, NDAC

## Fields
| Field | Description |
|-------|-------------|
| city | City name |
| county | County name |
| zip_code | 5-digit ZIP |
| ccn | CMS Certification Number (NONE for non-Medicare facilities) |
| service_type | AMBULATORY SURGICAL CENTER / HEMODIALYSIS / HOME HEMODIALYSIS / HOME PERITONEAL DIALYSIS / PUBLIC HEALTH CLINIC / NONE |
| facility_name | Full legal facility name |
| license_no | State license number (ASC###, ESRD###, HC###) |
| address | Street address |
| accreditation | Accreditation body (NONE, AAAHC, ACHC, TJC, NDAC, etc.) |
| phone | Phone number |
| fax | Fax number (may be empty) |
| licensee | Legal licensee entity |
| administrator | Administrator name and title |
| administration_address | c/o mailing address for administration |
| branches | Semicolon-separated branch location addresses (may be empty) |
| date_parsed | Date the script was run |
