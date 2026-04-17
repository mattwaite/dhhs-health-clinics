# Nebraska DHHS Health Clinic Facility Roster

Extracts the Nebraska Department of Health and Human Services licensed health clinic facility roster from PDF and converts it to a structured CSV.

**Source:** https://dhhs.ne.gov/licensure/Documents/HC_ASC_ESRD%20Lic%20Roster.pdf
**Update frequency:** Updated periodically by DHHS (last updated date is printed in the PDF header)

## Usage

```bash
pip install -r requirements.txt
python parse_health_clinics.py
```

The script downloads the current PDF, extracts all records, and writes output to `data/health_clinics_YYYY-MM-DD.csv`. The PDF is also saved to `pdfs/health_clinics_YYYY-MM-DD.pdf`.

## Output Fields

| Field | Description |
|-------|-------------|
| [fill in after /pdf-to-csv-parse] | |

## Testing

```bash
pytest test_parse_health_clinics.py -v
```

## Data Archive

PDFs are saved to `pdfs/` and CSVs to `data/`, both stamped with the run date.

## Facility Types Covered

- Ambulatory Surgical Centers (ASC)
- End Stage Renal Disease / Hemodialysis (ESRD)
- Health Clinics / Public Health Clinics (HC)
