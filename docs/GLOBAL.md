# Global coverage (opt-in)

```
bcf --global --help

--global   Opt-in. Also search non-FDA/EMA trial registries (ChiCTR, NMPA/CDE
           platform, other WHO ICTRP registries) and flag papers from other
           jurisdictions. Off by default.
           Records may come from research run under regulatory, ethics and data
           standards different from, and sometimes lighter than, US FDA or EU
           EMA standards; registry records can be less complete or less current.
           Every such record is labelled "non-FDA/EMA registry" with source and
           country, and JSON output adds registry_class and global_disclaimer.
           Inclusion is not an endorsement or recommendation and is not medical,
           legal or investment advice.
--global-sources LIST   limit to e.g. chictr,nmpa,ictrp

Phase 1 status (what --global does today):
  trials: link-outs only. Registry IDs found in ClinicalTrials.gov secondary
          IDs (e.g. ChiCTR, CTRI, jRCT, ISRCTN) are listed with a link; the
          foreign record itself is not fetched or stored. Direct ChiCTR,
          NMPA/CDE and WHO ICTRP data feeds are not enabled yet (terms/licence
          not cleared), so 'nmpa' currently matches nothing.
  papers: each paper gets jurisdiction_flag "non-FDA/EMA oversight" when an
          author-affiliation country is outside the US/EU/EEA, "unknown" when
          no country is found (never guessed).

```
