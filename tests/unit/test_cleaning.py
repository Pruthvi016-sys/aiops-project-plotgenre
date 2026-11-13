"""Text cleaning, parsing, genre mapping and record validation."""

import pytest

from plotgenre.data.cleaning import (clean_text, map_genres, parse_freebase_genres,
                                     parse_year, validate_record, word_count)

pytestmark = pytest.mark.unit
KW = {"Comedy": ["comedy"], "Romance": ["romance", "romantic"], "Crime": ["crime", "gangster"]}


def test_clean_text_strips_markup_urls_refs_and_whitespace():
    raw = "A <b>bold</b>  hero [12] visits http://x.org {{cite}}\n the   city."
    assert clean_text(raw) == "A bold hero visits the city."


@pytest.mark.parametrize("value", [None, ""])
def test_clean_text_empty(value):
    assert clean_text(value) == ""


@pytest.mark.parametrize("raw,year", [("1999", 1999), ("1999-05-21", 1999), ("2010-03", 2010),
                                      ("", None), (None, None), ("May 1999", None)])
def test_parse_year(raw, year):
    assert parse_year(raw) == year


def test_parse_freebase_genres_valid_and_invalid():
    parsed = parse_freebase_genres('{"/m/1": "Drama", "/m/2": "Crime Fiction"}')
    assert parsed == ["Drama", "Crime Fiction"]
    assert parse_freebase_genres("not json") == []
    assert parse_freebase_genres('["a list"]') == []
    assert parse_freebase_genres(None) == []


def test_map_genres_multi_label_and_dedup():
    assert map_genres(["Romantic comedy", "Gangster Film", "Crime Fiction"], KW) == [
        "Comedy", "Crime", "Romance"]
    assert map_genres(["Documentary"], KW) == []


def test_word_count():
    assert word_count("one two  three") == 3
    assert word_count("") == 0


@pytest.mark.parametrize("text,year,labels,reason", [
    ("", 1990, ["Drama"], "empty_text"),
    ("too short", 1990, ["Drama"], "too_short"),
    ("w " * 50, None, ["Drama"], "missing_year"),
    ("w " * 50, 1800, ["Drama"], "year_out_of_range"),
    ("w " * 50, 1990, [], "no_target_genre"),
    ("w " * 5000, 1990, ["Drama"], "too_long"),
    ("w " * 50, 1990, ["Drama"], None),
], ids=["empty_text", "too_short", "missing_year", "year_out_of_range",
        "no_target_genre", "too_long", "valid"])
def test_validate_record(text, year, labels, reason):
    assert validate_record(text.strip(), year, labels, 30, 3000, 1900, 2016) == reason
