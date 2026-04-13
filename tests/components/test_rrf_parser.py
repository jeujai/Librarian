"""Unit tests for the RRF parser module.

Tests cover parsing of MRCONSO, MRREL, MRSTY, MRDEF files,
filtering logic, malformed row handling, and validate_rrf_directory.
"""

import os
import tempfile

import pytest

from multimodal_librarian.components.knowledge_graph.rrf_parser import (
    MRCONSORow,
    MRDEFRow,
    MRRELRow,
    MRSTYRow,
    parse_mrconso,
    parse_mrdef,
    parse_mrrel,
    parse_mrsty,
    validate_rrf_directory,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_temp(lines, suffix=".RRF"):
    """Write lines to a temp file and return its path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    for line in lines:
        f.write(line + "\n")
    f.close()
    return f.name


def _mrconso_line(
    cui="C0000001", lat="ENG", ts="P", stt="PF", sab="SNOMEDCT_US",
    str_name="Aspirin", suppress="N",
):
    """Build a pipe-delimited MRCONSO row with 18 fields."""
    fields = [""] * 18
    fields[0] = cui
    fields[1] = lat
    fields[2] = ts
    fields[4] = stt
    fields[11] = sab
    fields[14] = str_name
    fields[16] = suppress
    return "|".join(fields)


def _mrrel_line(
    cui1="C0000001", rel="RO", cui2="C0000002", rela="may_treat",
    sab="SNOMEDCT_US",
):
    """Build a pipe-delimited MRREL row with 16 fields."""
    fields = [""] * 16
    fields[0] = cui1
    fields[3] = rel
    fields[4] = cui2
    fields[7] = rela
    fields[10] = sab
    return "|".join(fields)


def _mrsty_line(cui="C0000001", tui="T047"):
    """Build a pipe-delimited MRSTY row with 6 fields."""
    fields = [cui, tui, "", "", "", ""]
    return "|".join(fields)


def _mrdef_line(cui="C0000001", sab="SNOMEDCT_US", definition="A definition."):
    """Build a pipe-delimited MRDEF row with 6 fields."""
    fields = [""] * 6
    fields[0] = cui
    fields[4] = sab
    fields[5] = definition
    return "|".join(fields)


# ── MRCONSO parsing ─────────────────────────────────────────────────────────

class TestParseMrconso:
    """Tests for parse_mrconso."""

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            list(parse_mrconso("/nonexistent/MRCONSO.RRF"))

    def test_basic_parse(self):
        path = _write_temp([_mrconso_line()])
        try:
            rows = list(parse_mrconso(path))
            assert len(rows) == 1
            assert rows[0].cui == "C0000001"
            assert rows[0].lat == "ENG"
            assert rows[0].ts == "P"
            assert rows[0].stt == "PF"
            assert rows[0].sab == "SNOMEDCT_US"
            assert rows[0].str_name == "Aspirin"
            assert rows[0].suppress == "N"
        finally:
            os.unlink(path)

    def test_filters_non_english(self):
        lines = [
            _mrconso_line(cui="C0000001", lat="ENG"),
            _mrconso_line(cui="C0000002", lat="SPA"),
            _mrconso_line(cui="C0000003", lat="FRE"),
        ]
        path = _write_temp(lines)
        try:
            rows = list(parse_mrconso(path))
            assert len(rows) == 1
            assert rows[0].cui == "C0000001"
        finally:
            os.unlink(path)

    def test_filters_by_source_vocab(self):
        lines = [
            _mrconso_line(cui="C0000001", sab="SNOMEDCT_US"),
            _mrconso_line(cui="C0000002", sab="MSH"),
            _mrconso_line(cui="C0000003", sab="ICD9CM"),
        ]
        path = _write_temp(lines)
        try:
            rows = list(parse_mrconso(path, source_vocabs={"SNOMEDCT_US", "MSH"}))
            assert len(rows) == 2
            sabs = {r.sab for r in rows}
            assert sabs == {"SNOMEDCT_US", "MSH"}
        finally:
            os.unlink(path)

    def test_no_vocab_filter_returns_all_english(self):
        lines = [
            _mrconso_line(cui="C1", sab="SNOMEDCT_US"),
            _mrconso_line(cui="C2", sab="MSH"),
            _mrconso_line(cui="C3", sab="RXNORM"),
        ]
        path = _write_temp(lines)
        try:
            rows = list(parse_mrconso(path, source_vocabs=None))
            assert len(rows) == 3
        finally:
            os.unlink(path)

    def test_malformed_row_skipped(self):
        lines = [
            _mrconso_line(cui="C0000001"),
            "too|few|fields",
            _mrconso_line(cui="C0000002"),
        ]
        path = _write_temp(lines)
        try:
            rows = list(parse_mrconso(path))
            assert len(rows) == 2
            assert rows[0].cui == "C0000001"
            assert rows[1].cui == "C0000002"
        finally:
            os.unlink(path)

    def test_empty_file(self):
        path = _write_temp([])
        try:
            rows = list(parse_mrconso(path))
            assert rows == []
        finally:
            os.unlink(path)

    def test_blank_lines_skipped(self):
        lines = [
            _mrconso_line(cui="C1"),
            "",
            _mrconso_line(cui="C2"),
        ]
        path = _write_temp(lines)
        try:
            rows = list(parse_mrconso(path))
            assert len(rows) == 2
        finally:
            os.unlink(path)

    def test_returns_mrconso_row_dataclass(self):
        path = _write_temp([_mrconso_line()])
        try:
            rows = list(parse_mrconso(path))
            assert isinstance(rows[0], MRCONSORow)
        finally:
            os.unlink(path)


# ── MRREL parsing ────────────────────────────────────────────────────────────

class TestParseMrrel:
    """Tests for parse_mrrel."""

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            list(parse_mrrel("/nonexistent/MRREL.RRF"))

    def test_basic_parse(self):
        path = _write_temp([_mrrel_line()])
        try:
            rows = list(parse_mrrel(path))
            assert len(rows) == 1
            assert rows[0].cui1 == "C0000001"
            assert rows[0].rel == "RO"
            assert rows[0].cui2 == "C0000002"
            assert rows[0].rela == "may_treat"
            assert rows[0].sab == "SNOMEDCT_US"
        finally:
            os.unlink(path)

    def test_filters_by_source_vocab(self):
        lines = [
            _mrrel_line(sab="SNOMEDCT_US"),
            _mrrel_line(sab="MSH"),
            _mrrel_line(sab="ICD9CM"),
        ]
        path = _write_temp(lines)
        try:
            rows = list(parse_mrrel(path, source_vocabs={"SNOMEDCT_US"}))
            assert len(rows) == 1
            assert rows[0].sab == "SNOMEDCT_US"
        finally:
            os.unlink(path)

    def test_no_vocab_filter_returns_all(self):
        lines = [_mrrel_line(sab="A"), _mrrel_line(sab="B")]
        path = _write_temp(lines)
        try:
            rows = list(parse_mrrel(path))
            assert len(rows) == 2
        finally:
            os.unlink(path)

    def test_malformed_row_skipped(self):
        lines = [
            _mrrel_line(),
            "short|row",
            _mrrel_line(cui1="C9"),
        ]
        path = _write_temp(lines)
        try:
            rows = list(parse_mrrel(path))
            assert len(rows) == 2
        finally:
            os.unlink(path)

    def test_empty_file(self):
        path = _write_temp([])
        try:
            assert list(parse_mrrel(path)) == []
        finally:
            os.unlink(path)

    def test_returns_mrrel_row_dataclass(self):
        path = _write_temp([_mrrel_line()])
        try:
            rows = list(parse_mrrel(path))
            assert isinstance(rows[0], MRRELRow)
        finally:
            os.unlink(path)


# ── MRSTY parsing ────────────────────────────────────────────────────────────

class TestParseMrsty:
    """Tests for parse_mrsty."""

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            list(parse_mrsty("/nonexistent/MRSTY.RRF"))

    def test_basic_parse(self):
        path = _write_temp([_mrsty_line()])
        try:
            rows = list(parse_mrsty(path))
            assert len(rows) == 1
            assert rows[0].cui == "C0000001"
            assert rows[0].tui == "T047"
        finally:
            os.unlink(path)

    def test_malformed_row_skipped(self):
        lines = [
            _mrsty_line(),
            "only_one_field",
            _mrsty_line(cui="C2", tui="T048"),
        ]
        path = _write_temp(lines)
        try:
            rows = list(parse_mrsty(path))
            assert len(rows) == 2
        finally:
            os.unlink(path)

    def test_empty_file(self):
        path = _write_temp([])
        try:
            assert list(parse_mrsty(path)) == []
        finally:
            os.unlink(path)

    def test_returns_mrsty_row_dataclass(self):
        path = _write_temp([_mrsty_line()])
        try:
            rows = list(parse_mrsty(path))
            assert isinstance(rows[0], MRSTYRow)
        finally:
            os.unlink(path)


# ── MRDEF parsing ────────────────────────────────────────────────────────────

class TestParseMrdef:
    """Tests for parse_mrdef."""

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            list(parse_mrdef("/nonexistent/MRDEF.RRF"))

    def test_basic_parse(self):
        path = _write_temp([_mrdef_line()])
        try:
            rows = list(parse_mrdef(path))
            assert len(rows) == 1
            assert rows[0].cui == "C0000001"
            assert rows[0].sab == "SNOMEDCT_US"
            assert rows[0].definition == "A definition."
        finally:
            os.unlink(path)

    def test_filters_by_source_vocab(self):
        lines = [
            _mrdef_line(sab="SNOMEDCT_US"),
            _mrdef_line(sab="MSH"),
            _mrdef_line(sab="ICD9CM"),
        ]
        path = _write_temp(lines)
        try:
            rows = list(parse_mrdef(path, source_vocabs={"MSH"}))
            assert len(rows) == 1
            assert rows[0].sab == "MSH"
        finally:
            os.unlink(path)

    def test_no_vocab_filter_returns_all(self):
        lines = [_mrdef_line(sab="A"), _mrdef_line(sab="B")]
        path = _write_temp(lines)
        try:
            rows = list(parse_mrdef(path))
            assert len(rows) == 2
        finally:
            os.unlink(path)

    def test_malformed_row_skipped(self):
        lines = [
            _mrdef_line(),
            "too|few",
            _mrdef_line(cui="C2"),
        ]
        path = _write_temp(lines)
        try:
            rows = list(parse_mrdef(path))
            assert len(rows) == 2
        finally:
            os.unlink(path)

    def test_empty_file(self):
        path = _write_temp([])
        try:
            assert list(parse_mrdef(path)) == []
        finally:
            os.unlink(path)

    def test_returns_mrdef_row_dataclass(self):
        path = _write_temp([_mrdef_line()])
        try:
            rows = list(parse_mrdef(path))
            assert isinstance(rows[0], MRDEFRow)
        finally:
            os.unlink(path)


# ── validate_rrf_directory ───────────────────────────────────────────────────

class TestValidateRrfDirectory:
    """Tests for validate_rrf_directory."""

    def test_all_files_present(self, tmp_path):
        for name in ["MRCONSO.RRF", "MRREL.RRF", "MRSTY.RRF", "MRDEF.RRF", "SRDEF"]:
            (tmp_path / name).write_text("")
        found, missing = validate_rrf_directory(str(tmp_path))
        assert missing == []
        assert set(found.keys()) == {"MRCONSO.RRF", "MRREL.RRF", "MRSTY.RRF", "MRDEF.RRF", "SRDEF"}

    def test_missing_required_mrconso(self, tmp_path):
        (tmp_path / "MRREL.RRF").write_text("")
        found, missing = validate_rrf_directory(str(tmp_path))
        assert "MRCONSO.RRF" in missing

    def test_missing_required_mrrel(self, tmp_path):
        (tmp_path / "MRCONSO.RRF").write_text("")
        found, missing = validate_rrf_directory(str(tmp_path))
        assert "MRREL.RRF" in missing

    def test_both_required_missing(self, tmp_path):
        found, missing = validate_rrf_directory(str(tmp_path))
        assert "MRCONSO.RRF" in missing
        assert "MRREL.RRF" in missing

    def test_optional_files_not_in_missing(self, tmp_path):
        (tmp_path / "MRCONSO.RRF").write_text("")
        (tmp_path / "MRREL.RRF").write_text("")
        found, missing = validate_rrf_directory(str(tmp_path))
        assert missing == []
        # Optional files not found but not reported as missing
        assert "MRSTY.RRF" not in found
        assert "MRDEF.RRF" not in found
        assert "SRDEF" not in found

    def test_found_files_have_full_paths(self, tmp_path):
        (tmp_path / "MRCONSO.RRF").write_text("")
        (tmp_path / "MRREL.RRF").write_text("")
        found, _ = validate_rrf_directory(str(tmp_path))
        for name, full_path in found.items():
            assert full_path == os.path.join(str(tmp_path), name)

    def test_empty_directory(self, tmp_path):
        found, missing = validate_rrf_directory(str(tmp_path))
        assert len(found) == 0
        assert set(missing) == {"MRCONSO.RRF", "MRREL.RRF"}
