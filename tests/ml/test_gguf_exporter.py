"""
Property-based tests for GGUF exporter Modelfile generation.

# Feature: medical-knowledge-finetuning, Property 11: Modelfile contains required directives

Validates: Requirements 6.3
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from multimodal_librarian.ml.gguf_exporter import GGUFExporter
from multimodal_librarian.ml.models import ExportConfig

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------


def _gguf_filename() -> st.SearchStrategy[str]:
    """Generate a plausible GGUF filename (non-empty, ends with .gguf)."""
    return st.text(
        alphabet=st.sampled_from(
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789-_"
        ),
        min_size=1,
        max_size=80,
    ).map(lambda s: f"{s}.gguf")


def _model_name() -> st.SearchStrategy[str]:
    """Generate a plausible Ollama model name."""
    return st.text(
        alphabet=st.sampled_from(
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789-_."
        ),
        min_size=1,
        max_size=80,
    ).filter(lambda s: s.strip())


def _system_prompt() -> st.SearchStrategy[str]:
    """Generate a non-empty system prompt string.

    Excludes carriage-return (``\\r``) because Modelfiles are text files
    and ``\\r`` is normalised during write/read round-trips on all
    platforms.
    """
    return (
        st.text(min_size=1, max_size=500)
        .filter(lambda s: s.strip())
        .map(lambda s: s.replace("\r", ""))
        .filter(lambda s: s.strip())
    )


# ---------------------------------------------------------------------------
# Property 11: Modelfile contains required directives
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestModelfileContainsRequiredDirectives:
    """Property 11: Modelfile contains required directives.

    For any GGUF file path and model name, the generated Ollama Modelfile
    SHALL contain a FROM directive referencing the GGUF path, at least one
    PARAMETER directive, and a SYSTEM directive with a non-empty prompt.

    Validates: Requirements 6.3
    """

    @given(
        gguf_name=_gguf_filename(),
        model_name=_model_name(),
    )
    @settings(max_examples=100)
    def test_modelfile_contains_from_directive(
        self, gguf_name: str, model_name: str
    ) -> None:
        """The Modelfile contains a FROM directive referencing the GGUF path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            gguf_path = tmp_path / gguf_name
            gguf_path.touch()

            config = ExportConfig(
                output_dir=str(tmp_path),
                model_name=model_name,
            )
            exporter = GGUFExporter(config)
            modelfile_path = exporter._generate_modelfile(gguf_path, model_name)

            content = modelfile_path.read_text(encoding="utf-8")
            assert f"FROM {gguf_path.resolve()}" in content, (
                f"FROM directive not found or does not reference GGUF path.\n"
                f"Expected GGUF path: {gguf_path.resolve()}\n"
                f"Modelfile content:\n{content}"
            )

    @given(
        gguf_name=_gguf_filename(),
        model_name=_model_name(),
    )
    @settings(max_examples=100)
    def test_modelfile_contains_at_least_one_parameter_directive(
        self, gguf_name: str, model_name: str
    ) -> None:
        """The Modelfile contains at least one PARAMETER directive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            gguf_path = tmp_path / gguf_name
            gguf_path.touch()

            config = ExportConfig(
                output_dir=str(tmp_path),
                model_name=model_name,
            )
            exporter = GGUFExporter(config)
            modelfile_path = exporter._generate_modelfile(gguf_path, model_name)

            content = modelfile_path.read_text(encoding="utf-8")
            parameter_lines = [
                line
                for line in content.splitlines()
                if line.startswith("PARAMETER ")
            ]
            assert len(parameter_lines) >= 1, (
                f"Expected at least one PARAMETER directive.\n"
                f"Modelfile content:\n{content}"
            )

    @given(
        gguf_name=_gguf_filename(),
        model_name=_model_name(),
    )
    @settings(max_examples=100)
    def test_modelfile_contains_system_directive_with_non_empty_prompt(
        self, gguf_name: str, model_name: str
    ) -> None:
        """The Modelfile contains a SYSTEM directive with a non-empty prompt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            gguf_path = tmp_path / gguf_name
            gguf_path.touch()

            config = ExportConfig(
                output_dir=str(tmp_path),
                model_name=model_name,
            )
            exporter = GGUFExporter(config)
            modelfile_path = exporter._generate_modelfile(gguf_path, model_name)

            content = modelfile_path.read_text(encoding="utf-8")
            # SYSTEM directive may use triple-quoted or plain string
            assert "SYSTEM" in content, (
                f"SYSTEM directive not found in Modelfile.\n"
                f"Modelfile content:\n{content}"
            )
            # Extract the system prompt text after the SYSTEM keyword
            system_match = re.search(
                r'SYSTEM\s+"""(.+?)"""', content, re.DOTALL
            )
            if system_match is None:
                system_match = re.search(
                    r"SYSTEM\s+(.+)", content, re.DOTALL
                )
            assert system_match is not None, (
                f"Could not parse SYSTEM directive content.\n"
                f"Modelfile content:\n{content}"
            )
            prompt_text = system_match.group(1).strip()
            assert len(prompt_text) > 0, (
                f"SYSTEM directive has an empty prompt.\n"
                f"Modelfile content:\n{content}"
            )

    @given(
        gguf_name=_gguf_filename(),
        model_name=_model_name(),
        custom_prompt=_system_prompt(),
    )
    @settings(max_examples=100)
    def test_modelfile_uses_custom_system_prompt_when_provided(
        self, gguf_name: str, model_name: str, custom_prompt: str
    ) -> None:
        """When a custom system prompt is configured, the Modelfile uses it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            gguf_path = tmp_path / gguf_name
            gguf_path.touch()

            config = ExportConfig(
                output_dir=str(tmp_path),
                model_name=model_name,
                system_prompt=custom_prompt,
            )
            exporter = GGUFExporter(config)
            modelfile_path = exporter._generate_modelfile(gguf_path, model_name)

            content = modelfile_path.read_text(encoding="utf-8")
            assert custom_prompt in content, (
                f"Custom system prompt not found in Modelfile.\n"
                f"Custom prompt: {custom_prompt!r}\n"
                f"Modelfile content:\n{content}"
            )

    @given(
        gguf_name=_gguf_filename(),
        model_name=_model_name(),
    )
    @settings(max_examples=100)
    def test_modelfile_contains_all_required_directives(
        self, gguf_name: str, model_name: str
    ) -> None:
        """The Modelfile contains FROM, at least one PARAMETER, and SYSTEM."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            gguf_path = tmp_path / gguf_name
            gguf_path.touch()

            config = ExportConfig(
                output_dir=str(tmp_path),
                model_name=model_name,
            )
            exporter = GGUFExporter(config)
            modelfile_path = exporter._generate_modelfile(gguf_path, model_name)

            content = modelfile_path.read_text(encoding="utf-8")
            lines = content.splitlines()

            has_from = any(line.startswith("FROM ") for line in lines)
            has_parameter = any(
                line.startswith("PARAMETER ") for line in lines
            )
            has_system = any(line.startswith("SYSTEM") for line in lines)

            assert has_from, f"Missing FROM directive.\nContent:\n{content}"
            assert has_parameter, (
                f"Missing PARAMETER directive.\nContent:\n{content}"
            )
            assert has_system, (
                f"Missing SYSTEM directive.\nContent:\n{content}"
            )
