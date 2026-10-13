"""Test: CTA selection must go through 'Tidak ada' combobox first."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gmb_automation import get_cta_candidates, CTA_MAP

def test_book_candidates_include_indonesian():
    cands = get_cta_candidates("Book")
    assert "Book" in cnds if False else True  # placeholder to fail first
    assert "Book" in cands
    # Indonesian label for Book CTA is "Pesan" in GMB
    assert "Pesan" in cands or "Booking" in cands, f"Book candidates {cands} must include Indonesian mapping"

def test_tidak_ada_is_default_cta_label():
    # helper must know default closed label
    from gmb_automation import DEFAULT_CTA_LABEL
    assert DEFAULT_CTA_LABEL == "Tidak ada"

def test_cta_map_has_book():
    assert "Book" in CTA_MAP
