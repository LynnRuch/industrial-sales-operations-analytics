# 2026 Census ZCTA — Source Validation

## Source

- Provider: U.S. Census Bureau
- Dataset: 2026 National ZIP Code Tabulation Areas Gazetteer
- Archive: `2026_Gaz_zcta_national.zip`
- Internal file: `2026_Gaz_zcta_national.txt`
- Format: Pipe-delimited text in a compressed ZIP archive
- Source URL: https://www.census.gov/geographies/reference-files/2026/geo/gazetter-file.html

## Development Environment

- Fedora Linux
- Python 3.12
- Visual Studio Code
- pandas

## Structural Validation Results

| Check | Result |
|---|---:|
| Total records | 33,791 |
| Unique geographic identifiers | 33,791 |
| Duplicate identifiers | 0 |
| Invalid five-digit identifiers | 0 |
| Missing coordinates | 0 |
| Invalid coordinate ranges | 0 |

**Status: PASS**

The results above document the structural validation performed on the Census ZCTA reference dataset during project development. The original standalone inspection script is not included in the published source files.

## Geographic Coverage

- Minimum latitude: -14.324678
- Maximum latitude: 71.264374
- Minimum longitude: -176.632435
- Maximum longitude: 145.754396

## Important Limitations

Census ZIP Code Tabulation Areas (ZCTAs) are not equivalent to USPS delivery ZIP codes.

The representative coordinates are geographic reference points, not actual customer shipping addresses.

This dataset does not independently establish whether a ZIP code accepts physical shipments.

## Subsequent Project Processing

Following the initial source validation, the project developed additional Python scripts to prepare geographic reference data and support ZIP-based sales territory assignments.

Relevant source files include:

- `src/etl/build_zip_reference.py`
- `src/generation/build_industrial_zip_reference.py`
- `src/generation/build_shipping_zip_reference.py`
- `src/generation/build_zip_territory_assignments.py`

These scripts are included in the project repository. The Census validation results documented above should not be interpreted as independent verification of USPS delivery eligibility or every ZIP classification.