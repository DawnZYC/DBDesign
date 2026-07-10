# assets/ — bundled template (supply your own)

The Convert feature uses a bundled EcoTEA template as the default output template:

    backend/app/assets/ecotea_template.xlsx

This file contains confidential data structure and is **gitignored** (not committed). To run
Convert with the bundled default, place your own `ecotea_template.xlsx` here. Otherwise, upload a
template per request via the Convert UI / `POST /api/convert` (the `ecotea_template` field) — the
backend returns a clear error when no template is available.
