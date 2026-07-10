# Energy-Model Domain Knowledge (example / sanitized)

> This is a **sanitized placeholder** for the RAG knowledge source. The real
> `domain_knowledge.md` is confidential and gitignored — supply your own copy at
> `backend/data/domain_knowledge.md`. All codes/values below are fictional and only show
> the expected structure (split by `##` headings, ~200-500 words per section).

## Unit conversion — Energy units

Conversions between energy units (per IEA conventions):

- 1 PJ (petajoule, 10^15 J) ≈ 23.885 ktoe (thousand tonnes of oil equivalent)
- 1 ktoe ≈ 0.041868 PJ
- 1 GWh (gigawatt-hour) = 0.0036 PJ
- 1 PJ = 277.778 GWh
- 1 MWh = 3.6 GJ = 0.0036 PJ

Energy commodities (commodity_set = NRG) default to the unit **PJ**; electricity-related
quantities sometimes use GWh / MWh.

## Unit conversion — CO2 emissions

- kt-CO2 is the standard unit for emission commodities (commodity_set = ENV)
- 1 Mt-CO2 = 1000 kt-CO2
- The emission factor unit is usually kg-CO2 / GJ or kt-CO2 / PJ (numerically equal)

CO2 quantities cannot be converted directly to energy units; multiply by the emission factor.

## Unit conversion — Currency

Costs use a fixed base currency (e.g. `BASECUR`):
- CAPEX: M$ / GW · Fixed OPEX: M$ / GW-yr · Variable OPEX: M$ / PJ

## Commodity Set — NRG energy commodities (fictional codes)

- **COAL01** — coal for power generation
- **NGAS01** — natural gas for power generation
- **BIOMASS01** — biomass for power generation
- **SOLAR01** — solar power
- **HYDROGEN01** — hydrogen energy

## Commodity Set — ENV emission commodities (fictional codes)

- **CO2_01** — direct CO2 emitted by power generation
- **CO2_CCS01** — CO2 captured via CCS

## Sectors

The model covers 10 sectors (matching the workbook sheets): Power, Industry, Primary,
Transport, Water, Waste, Building, Household, Agri, InfoComm.

## Time-slice level CTSLvl

CTSLvl indicates the time granularity a commodity is modeled at: DAYNITE (day/night),
SEASON, WEEKLY, ANNUAL (default).

## CCS pathway terminology

Carbon capture, utilization and storage: **Capture** (separate CO2 from flue gas),
**Storage** (inject underground), **Utilization** (use CO2 to make products).

## Technology-code naming convention

An 11-char `technology_code`: first 3 = process category (e.g. PWR=power), middle 3 =
fuel/medium, last 3 = technology form, 2-char suffix = version. Example: `NGCC01` =
natural-gas combined cycle, version 01.
