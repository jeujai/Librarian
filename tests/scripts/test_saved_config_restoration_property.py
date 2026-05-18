"""
Property-based tests for saved config restoration with CLI override
precedence.

# Feature: data-generation-resume, Property 6: Saved config restoration
#   with CLI override precedence

Validates: Requirements 8.2, 8.3

Property 6 states: For any saved config dict S and any set of explicit
CLI overrides E, the merged result equals S overridden by E.  That is,
for each parameter p:
  - if p ∈ E then merged[p] == E[p]
  - else merged[p] == S[p]
Parameters not present in either S or E retain the parser's default
values.

The test exercises ``_apply_saved_config()`` from
``scripts/run-training-pipeline.py`` directly.
"""

from __future__ import annotations

import argparse
import importlib
import sys
import types
from pathlib import Path
from typing import Any, Dict, Set

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Import the function under test from the pipeline script
# ---------------------------------------------------------------------------

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run-training-pipeline.py"


def _load_pipeline_module() -> types.ModuleType:
    """Import ``run-training-pipeline.py`` as a module.

    The script uses a hyphenated filename which is not a valid Python
    identifier, so we use ``importlib`` to load it manually.
    """
    spec = importlib.util.spec_from_file_location(
        "run_training_pipeline", str(_SCRIPT_PATH)
    )
    assert spec is not None, f"Could not find {_SCRIPT_PATH}"
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Prevent the script's ``if __name__ == '__main__'`` block from
    # executing during import.
    mod.__name__ = "run_training_pipeline"
    spec.loader.exec_module(mod)
    return mod


_pipeline = _load_pipeline_module()
_apply_saved_config = _pipeline._apply_saved_config
_build_parser = _pipeline.build_parser

# ---------------------------------------------------------------------------
# Discover the parser's known argument names and their defaults
# ---------------------------------------------------------------------------

_parser = _build_parser()
_PARSER_DEFAULTS: Dict[str, Any] = {
    k: v for k, v in vars(_parser.parse_args([])).items()
}
_ALL_ARG_NAMES: list[str] = list(_PARSER_DEFAULTS.keys())

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Values that can appear in a saved config or as CLI overrides.
# We keep them simple — the function is type-agnostic (it just does
# ``setattr``), so the important thing is identity, not type fidelity.
_config_value = st.one_of(
    st.integers(min_value=0, max_value=10_000),
    st.floats(
        min_value=0.0,
        max_value=1.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    st.text(min_size=1, max_size=30).filter(lambda s: s.strip()),
    st.booleans(),
    st.none(),
    st.lists(st.text(min_size=1, max_size=15), min_size=1, max_size=4),
)


def _saved_config_strategy() -> st.SearchStrategy[Dict[str, Any]]:
    """Generate a random saved-config dict whose keys are a subset of
    the parser's known argument names.
    """
    return st.dictionaries(
        keys=st.sampled_from(_ALL_ARG_NAMES),
        values=_config_value,
        min_size=1,
        max_size=min(len(_ALL_ARG_NAMES), 15),
    )


def _explicit_args_strategy(
    saved_config: Dict[str, Any],
) -> st.SearchStrategy[Set[str]]:
    """Generate a random subset of argument names to mark as
    explicitly provided.  May include keys that are in the saved
    config, keys that are not, or be empty.
    """
    return st.frozensets(
        st.sampled_from(_ALL_ARG_NAMES),
        min_size=0,
        max_size=min(len(_ALL_ARG_NAMES), 10),
    ).map(set)


def _namespace_from_defaults_and_overrides(
    overrides: Dict[str, Any],
) -> argparse.Namespace:
    """Build an ``argparse.Namespace`` starting from parser defaults
    and applying *overrides* on top (simulating explicit CLI args).
    """
    ns_dict = dict(_PARSER_DEFAULTS)
    ns_dict.update(overrides)
    return argparse.Namespace(**ns_dict)


# ---------------------------------------------------------------------------
# Property 6: Saved config restoration with CLI override precedence
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestSavedConfigRestorationProperty:
    """Property 6: Saved config restoration with CLI override precedence.

    For any saved config dict S and any set of explicit CLI overrides E,
    the merged configuration SHALL equal S overridden by E: explicit
    args always win, non-explicit args are restored from saved config.

    Tag: Feature: data-generation-resume, Property 6: Saved config
         restoration with CLI override precedence
    Validates: Requirements 8.2, 8.3
    """

    # ------------------------------------------------------------------
    # Core property: explicit args always win over saved config
    # ------------------------------------------------------------------

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_explicit_args_override_saved_config(
        self,
        data: st.DataObject,
    ) -> None:
        """For every parameter p that is in explicit_args, the merged
        result must equal the original CLI value, not the saved config
        value.
        """
        saved_config = data.draw(_saved_config_strategy(), label="saved_config")
        explicit_args: Set[str] = data.draw(
            _explicit_args_strategy(saved_config), label="explicit_args"
        )

        # Build explicit override values that differ from saved config
        # so we can distinguish which source won.
        explicit_overrides: Dict[str, Any] = {}
        for key in explicit_args:
            # Use a sentinel that is guaranteed different from saved
            explicit_overrides[key] = f"__explicit_{key}__"

        args = _namespace_from_defaults_and_overrides(explicit_overrides)
        original_explicit_values = {
            k: getattr(args, k) for k in explicit_args if hasattr(args, k)
        }

        merged = _apply_saved_config(args, saved_config, explicit_args)

        for key in explicit_args:
            if not hasattr(merged, key):
                continue
            assert getattr(merged, key) == original_explicit_values[key], (
                f"Explicit arg '{key}' was overwritten by saved config. "
                f"Expected {original_explicit_values[key]!r}, "
                f"got {getattr(merged, key)!r}"
            )

    # ------------------------------------------------------------------
    # Core property: non-explicit args are restored from saved config
    # ------------------------------------------------------------------

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_non_explicit_args_restored_from_saved_config(
        self,
        data: st.DataObject,
    ) -> None:
        """For every parameter p that is in saved_config but NOT in
        explicit_args, the merged result must equal the saved config
        value.
        """
        saved_config = data.draw(_saved_config_strategy(), label="saved_config")
        explicit_args: Set[str] = data.draw(
            _explicit_args_strategy(saved_config), label="explicit_args"
        )

        args = _namespace_from_defaults_and_overrides({})
        merged = _apply_saved_config(args, saved_config, explicit_args)

        for key, saved_value in saved_config.items():
            if key in explicit_args:
                continue
            if not hasattr(merged, key):
                continue
            assert getattr(merged, key) == saved_value, (
                f"Non-explicit arg '{key}' was not restored from saved "
                f"config. Expected {saved_value!r}, "
                f"got {getattr(merged, key)!r}"
            )

    # ------------------------------------------------------------------
    # Combined: merged == S overridden by E
    # ------------------------------------------------------------------

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_merged_equals_saved_overridden_by_explicit(
        self,
        data: st.DataObject,
    ) -> None:
        """The merged namespace, for every key present in either S or E,
        equals S[key] when key ∉ E, and the original CLI value when
        key ∈ E.
        """
        saved_config = data.draw(_saved_config_strategy(), label="saved_config")
        explicit_args: Set[str] = data.draw(
            _explicit_args_strategy(saved_config), label="explicit_args"
        )

        # Build explicit overrides with distinguishable sentinel values
        explicit_overrides: Dict[str, Any] = {
            k: f"__explicit_{k}__" for k in explicit_args
        }

        args = _namespace_from_defaults_and_overrides(explicit_overrides)
        # Snapshot the pre-merge state for explicit args
        pre_merge_values = dict(vars(args))

        merged = _apply_saved_config(args, saved_config, explicit_args)

        for key in set(saved_config.keys()) | explicit_args:
            if not hasattr(merged, key):
                continue
            actual = getattr(merged, key)
            if key in explicit_args:
                expected = pre_merge_values[key]
                assert actual == expected, (
                    f"Key '{key}' is explicit — expected CLI value "
                    f"{expected!r}, got {actual!r}"
                )
            else:
                expected = saved_config[key]
                assert actual == expected, (
                    f"Key '{key}' is non-explicit — expected saved "
                    f"config value {expected!r}, got {actual!r}"
                )

    # ------------------------------------------------------------------
    # Keys not in saved config or explicit args retain defaults
    # ------------------------------------------------------------------

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_untouched_args_retain_parser_defaults(
        self,
        data: st.DataObject,
    ) -> None:
        """Parameters not present in either the saved config or the
        explicit args set retain the parser's default values.
        """
        saved_config = data.draw(_saved_config_strategy(), label="saved_config")
        explicit_args: Set[str] = data.draw(
            _explicit_args_strategy(saved_config), label="explicit_args"
        )

        args = _namespace_from_defaults_and_overrides({})
        merged = _apply_saved_config(args, saved_config, explicit_args)

        touched_keys = set(saved_config.keys()) | explicit_args
        for key in _ALL_ARG_NAMES:
            if key in touched_keys:
                continue
            assert getattr(merged, key) == _PARSER_DEFAULTS[key], (
                f"Untouched arg '{key}' changed from default "
                f"{_PARSER_DEFAULTS[key]!r} to {getattr(merged, key)!r}"
            )

    # ------------------------------------------------------------------
    # Saved config keys not in parser are silently ignored
    # ------------------------------------------------------------------

    @given(
        unknown_keys=st.dictionaries(
            keys=st.text(min_size=5, max_size=20).filter(
                lambda s: (
                    s.isidentifier()
                    and s not in _PARSER_DEFAULTS
                    and not s.startswith("__")  # exclude dunder attrs
                )
            ),
            values=_config_value,
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_unknown_saved_config_keys_are_ignored(
        self,
        unknown_keys: Dict[str, Any],
    ) -> None:
        """Keys in the saved config that do not correspond to any
        parser argument are silently ignored — they must not appear
        on the merged namespace.
        """
        args = _namespace_from_defaults_and_overrides({})
        original_keys = set(vars(args).keys())

        merged = _apply_saved_config(args, unknown_keys, set())

        # No new attributes should have been added
        merged_keys = set(vars(merged).keys())
        assert merged_keys == original_keys, (
            f"Unknown keys leaked into namespace: "
            f"{merged_keys - original_keys}"
        )

    # ------------------------------------------------------------------
    # Empty saved config leaves args unchanged
    # ------------------------------------------------------------------

    @given(
        explicit_args=st.frozensets(
            st.sampled_from(_ALL_ARG_NAMES),
            min_size=0,
            max_size=5,
        ).map(set),
    )
    @settings(max_examples=100, deadline=None)
    def test_empty_saved_config_leaves_args_unchanged(
        self,
        explicit_args: Set[str],
    ) -> None:
        """An empty saved config dict does not modify any argument."""
        args = _namespace_from_defaults_and_overrides({})
        snapshot = dict(vars(args))

        merged = _apply_saved_config(args, {}, explicit_args)

        assert vars(merged) == snapshot, (
            "Empty saved config modified the namespace"
        )

    # ------------------------------------------------------------------
    # All args explicit → saved config has no effect
    # ------------------------------------------------------------------

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_all_args_explicit_ignores_saved_config(
        self,
        data: st.DataObject,
    ) -> None:
        """When every parser argument is marked as explicit, the saved
        config has zero effect on the merged result.
        """
        saved_config = data.draw(_saved_config_strategy(), label="saved_config")
        all_explicit = set(_ALL_ARG_NAMES)

        explicit_overrides = {k: f"__explicit_{k}__" for k in all_explicit}
        args = _namespace_from_defaults_and_overrides(explicit_overrides)
        snapshot = dict(vars(args))

        merged = _apply_saved_config(args, saved_config, all_explicit)

        assert vars(merged) == snapshot, (
            "Saved config modified namespace despite all args being explicit"
        )

    # ------------------------------------------------------------------
    # No args explicit → saved config fully applied
    # ------------------------------------------------------------------

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_no_args_explicit_fully_applies_saved_config(
        self,
        data: st.DataObject,
    ) -> None:
        """When no arguments are marked as explicit, every key in the
        saved config is applied to the namespace.
        """
        saved_config = data.draw(_saved_config_strategy(), label="saved_config")

        args = _namespace_from_defaults_and_overrides({})
        merged = _apply_saved_config(args, saved_config, set())

        for key, saved_value in saved_config.items():
            if not hasattr(merged, key):
                continue
            assert getattr(merged, key) == saved_value, (
                f"Key '{key}' was not restored from saved config. "
                f"Expected {saved_value!r}, got {getattr(merged, key)!r}"
            )

    # ------------------------------------------------------------------
    # Function returns the same namespace object (mutates in place)
    # ------------------------------------------------------------------

    def test_returns_same_namespace_object(self) -> None:
        """``_apply_saved_config`` mutates and returns the same
        ``argparse.Namespace`` object it received.
        """
        args = _namespace_from_defaults_and_overrides({})
        saved_config = {"pair_count": 9999}

        result = _apply_saved_config(args, saved_config, set())

        assert result is args, (
            "_apply_saved_config returned a different object"
        )
