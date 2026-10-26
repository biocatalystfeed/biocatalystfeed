# Global coverage (opt-in)

```
bcf --global --help

--global   Opt-in. Also link to records in non-FDA/EMA trial registries
           (e.g. China's ChiCTR and other WHO-listed national registries,
           via IDs that ClinicalTrials.gov lists) and flag papers from other
           jurisdictions. Off by default.
           Records may come from research run under regulatory, ethics and data
           standards different from, and sometimes lighter than, US FDA or EU
           EMA standards; registry records can be less complete or less current.
           Every such record is labelled "non-FDA/EMA registry" with source and
           country, and JSON output adds registry_class and global_disclaimer.
           Inclusion is not an endorsement or recommendation and is not medical,
           legal or investment advice.
--global-sources LIST   limit to e.g. chictr,ictrp

```
