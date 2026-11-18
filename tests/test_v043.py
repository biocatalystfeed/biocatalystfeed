"""0.4.3: market-wide fda_approvals no longer truncates at 500 applications (fda_decisions approvals were missing)."""
from fdawatch import core


class _Stub:
    def __init__(self): self.calls = []

    def drugsfda(self, sponsors=None, application_number=None, since=None, until=None, max_records=500):
        self.calls.append(max_records)
        return []


def test_market_wide_cap_is_high():
    s = _Stub()
    core.fda_approvals(s, since="2026-08-01")
    assert s.calls == [5000]


def test_targeted_cap_unchanged_and_override():
    s = _Stub()
    core.fda_approvals(s, application_number="NDA217806")
    core.fda_approvals(s, since="2026-08-01", max_apps=50)
    assert s.calls == [500, 50]


def test_drug_of_skips_common_words():
    from decisionwatch.core import drug_of
    assert drug_of("the PDUFA date for the treatment of the disease is March 1, 2027") is None
    assert drug_of("a kinase inhibitor; press release; PDUFA target action date for bezuclastinib") == "bezuclastinib"
    assert drug_of("rare disease drug ZEPBOUND (tirzepatide) PDUFA") == "tirzepatide"
    assert drug_of("participants with disease; lorundrostat PDUFA") == "lorundrostat"
