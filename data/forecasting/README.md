# Public-study provenance

`sources.json` is the audit manifest. It records files actually retrieved on
2026-10-28, their SHA256 hashes, licenses and inclusion decisions. Full scientific
and privacy limitations are in `docs/FORECAST_DATA_INVENTORY.md`.

Only checksum-pinned QDE and SpectroPhon inputs are supported by
`python3 -m ai.forecasting.ingestion`. Use an **external cache directory** and
`--delete-raw`; never upload or commit source workbooks, XPTs, or participant rows.
SpectroPhon contains private identity columns despite its filename: the importer
consults them locally only for conservative grouping, then exports no names or
name hashes. Equal/missing identity keys remain grouped to reduce leakage.

Retain attribution in any redistributed derived database or model report:
Michael Kirby (2021), SpectroPhon DBM Subject Data v1,
https://doi.org/10.17632/jt22782wjh.1 (CC BY 4.0); PhysioNet QDE v1.0.0,
https://doi.org/10.13026/C23082 (ODC Attribution 1.0), and the research citations
listed on its source page. Changes: local numeric allowlisting, new anonymous IDs,
unit conversion, group normalization and cumulative mass-proxy calculation.

Licenses allow statistical reuse under their conditions; they do not validate
measurement quality, consent, clinical applicability, or model recommendations.
