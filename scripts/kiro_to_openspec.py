#!/usr/bin/env python3
"""
Convert Kiro specs (.kiro/specs/) to OpenSpec format (openspec/specs/).

Each Kiro spec directory (design.md + requirements.md/bugfix.md + tasks.md) is
converted to an OpenSpec capability directory with spec.md (Purpose + Requirements).
"""

import re
import shutil
from pathlib import Path

PROJECT_ROOT = Path("/Volumes/CORSAIR/librarian")
KIRO_SPECS = PROJECT_ROOT / ".kiro" / "specs"
OPENSPEC_SPECS = PROJECT_ROOT / "openspec" / "specs"

# Helper: match ## section header (2 hashes exactly — not 3+)
H2 = r"(?<!#)##\s+"
# Helper: match ### subsection header (3 hashes exactly — not 4+)
H3 = r"(?<!#)###\s+"


def sanitize_name(text: str) -> str:
    return text.strip().rstrip(".")


def extract_purpose_from_requirements(content: str) -> str:
    """Extract Purpose from requirements.md (Introduction/Overview/Glossary)."""
    parts = []

    # Introduction
    m = re.search(
        rf"{H2}Introduction\s*\n(.*?)(?={H2}(?:Glossary|(?:\S+\s+)?Requirements|User Stories|Problem|Technical))",
        content, re.DOTALL
    )
    if m:
        parts.append(m.group(1).strip())

    # Overview (fallback)
    if not parts:
        m = re.search(
            rf"{H2}Overview\s*\n(.*?)(?={H2}(?:Problem|User Stories|(?:\S+\s+)?Requirements|Technical|Glossary|Current|Data Flow|User Experience))",
            content, re.DOTALL
        )
        if m:
            parts.append(m.group(1).strip())

    # Problem Statement
    m = re.search(
        rf"{H2}Problem Statement\s*\n(.*?)(?={H2}(?:User Stories|Requirements|Technical|Out of Scope))",
        content, re.DOTALL
    )
    if m:
        text = m.group(1).strip()
        if text:
            parts.append("\n### Problem Statement\n" + text)

    # Glossary
    m = re.search(
        rf"{H2}Glossary\s*\n(.*?)(?={H2}(?:Requirements|User Stories))",
        content, re.DOTALL
    )
    if m:
        terms = re.findall(r"-\s+\*\*([^*]+)\*\*:\s*(.+)", m.group(1))
        if terms:
            lines = ["\n### Key Terms"]
            for term, definition in terms:
                lines.append(f"- **{term.strip()}**: {definition.strip()}")
            parts.append("\n".join(lines))

    # Last resort: first paragraph
    if not parts:
        m = re.search(r"^#\s+.*?\n\n(.*?)(?=\n(?<!#)##|\Z)", content, re.DOTALL)
        if m:
            parts.append(m.group(1).strip())

    purpose = "\n\n".join(parts).strip()
    if len(purpose) < 50:
        m = re.search(r"^#\s+(.*)", content, re.MULTILINE)
        if m:
            purpose = f"This capability defines the requirements for: {m.group(1).strip()}.\n\n{purpose}"
    return purpose


def extract_purpose_from_bugfix(content: str) -> str:
    """Extract Purpose from bugfix.md (Introduction/Summary)."""
    parts = []

    # Introduction
    m = re.search(
        rf"{H2}Introduction\s*\n(.*?)(?={H2}Bug Analysis)",
        content, re.DOTALL
    )
    if m:
        parts.append(m.group(1).strip())

    # Summary (simpler bugfix format)
    if not parts:
        m = re.search(
            rf"{H2}Summary\s*\n(.*?)(?={H2}(?:Root Cause|Affected Code|Expected Behavior|Bug \d|Impact))",
            content, re.DOTALL
        )
        if m:
            parts.append(m.group(1).strip())

    # Current Behavior as context
    m = re.search(
        rf"{H3}Current Behavior.*?\n(.*?)(?={H3}Expected Behavior)",
        content, re.DOTALL
    )
    if m:
        parts.append("\n### Defect Description\n" + m.group(1).strip())

    # First paragraph fallback
    if not parts:
        m = re.search(r"^#\s+.*?\n\n(.*?)(?=\n(?<!#)##|\Z)", content, re.DOTALL)
        if m:
            parts.append(m.group(1).strip())

    purpose = "\n\n".join(parts).strip()
    if len(purpose) < 50:
        m = re.search(r"^#\s+(.*)", content, re.MULTILINE)
        if m:
            purpose = f"This bugfix addresses: {m.group(1).strip()}.\n\n{purpose}"
    return purpose


def parse_acceptance_criteria(ac_text: str) -> list[dict]:
    """Parse acceptance criteria into OpenSpec GIVEN/WHEN/THEN scenarios.

    Handles both numbered ("1. text") and bulleted ("- text") formats.
    """
    scenarios = []
    # Try numbered format first: "1. text"
    items = re.findall(r"\d+\.\s+(.*?)(?=\d+\.\s+|\Z)", ac_text, re.DOTALL)
    # If no numbered items, try bulleted format: "- text" (possibly indented)
    if not items:
        items = re.findall(r"^\s*-\s+(.*?)(?=^\s*-\s+|\Z)", ac_text, re.DOTALL | re.MULTILINE)

    for item in items:
        text = item.strip().replace("\n", " ").replace("  ", " ")
        steps = []

        when_m = re.search(r"WHEN\s+(.*?)(?:THEN\s+|THE\s+|SHALL\s+)", text)
        then_m = re.search(r"THEN\s+(.*)", text)

        if when_m and then_m:
            steps.append(f"- **WHEN** {when_m.group(1).strip().rstrip(',')}")
            steps.append(f"- **THEN** {then_m.group(1).strip()}")
        elif re.search(r"\bSHALL\b", text):
            given_m = re.search(r"(?:IF|FOR|GIVEN)\s+(.*?)(?:THEN|THE|SHALL)", text)
            if given_m:
                steps.append(f"- **GIVEN** {given_m.group(1).strip().rstrip(',')}")
            steps.append(f"- **THEN** {text.strip()}")
        elif re.search(r"\bMUST\b", text):
            steps.append(f"- **THEN** {text.strip()}")
        else:
            steps.append(f"- **THEN** {text.strip()}")

        name = f"Scenario: {text[:60].strip()}"
        if len(name) > 75:
            name = name[:72] + "..."

        scenarios.append({"name": name, "steps": steps})

    return scenarios


def parse_bugfix_behaviors(content: str, section: str) -> list[dict]:
    """Parse formal bugfix.md Expected/Unchanged Behavior into scenarios."""
    scenarios = []
    pattern = (
        rf"{H3}Expected Behavior.*?\n(.*?)(?={H3}Unchanged Behavior|\Z)"
        if section == "expected"
        else rf"{H3}Unchanged Behavior.*?\n(.*?)(?=\Z)"
    )
    m = re.search(pattern, content, re.DOTALL)
    if not m:
        return scenarios

    items = re.findall(r"(\d+\.\d+)\s+(.*?)(?=\d+\.\d+\s+|\Z)", m.group(1), re.DOTALL)
    for num, text in items:
        text = text.strip().replace("\n", " ").replace("  ", " ")
        steps = []
        when_m = re.search(r"WHEN\s+(.*?)(?:THEN\s+|THE\s+|SHALL\s+)", text)
        shall_m = re.search(r"SHALL\s+(.*)", text)
        continue_m = re.search(r"SHALL\s+CONTINUE\s+TO\s+(.*)", text)

        if when_m and continue_m:
            steps.append(f"- **WHEN** {when_m.group(1).strip().rstrip(',')}")
            steps.append(f"- **THEN** the system SHALL CONTINUE TO {continue_m.group(1).strip()}")
        elif when_m and shall_m:
            steps.append(f"- **WHEN** {when_m.group(1).strip().rstrip(',')}")
            steps.append(f"- **THEN** the system SHALL {shall_m.group(1).strip()}")
        elif re.search(r"\bSHALL\b", text):
            steps.append(f"- **THEN** {text.strip()}")
        else:
            steps.append(f"- **THEN** {text.strip()}")

        name = f"Scenario {num}"
        if len(text) < 80:
            name = f"Scenario {num}: {text[:60].strip()}"
        scenarios.append({"name": name, "steps": steps})

    return scenarios


def parse_requirements_section(content: str) -> list[dict]:
    """Parse ## Requirements / ## User Stories into OpenSpec requirement blocks."""
    requirements = []

    # Find the requirements section (handles "Requirements", "User Stories",
    # "Implementation Requirements", "Technical Requirements", etc.)
    m = re.search(
        rf"{H2}(?:\S+\s+)?(?:Requirements|User Stories)\s*\n"
        rf"(.*?)(?={H2}(?:Technical|Out of Scope|Notes|Validation|Success|Implementation Phases|Risk|Future|File Structure|Database Schema)|\Z)",
        content, re.DOTALL
    )
    if not m:
        # Fallback: scan the entire document for ### requirements
        req_section = content
    else:
        req_section = m.group(1)

    # Parse the section into requirement blocks
    parsed = _parse_requirement_blocks(req_section)

    # If the section-based parse yielded nothing, fall back to scanning full content
    if not parsed and m:
        parsed = _parse_requirement_blocks(content)

    return parsed


def _parse_requirement_blocks(req_section: str) -> list[dict]:
    """Parse ### blocks from a section of text into requirements."""
    requirements = []

    # Split by ### headers (must be at line start, exactly 3 hashes)
    req_blocks = re.split(r"(?m)^(?=###\s+)", req_section)

    for block in req_blocks:
        block = block.strip()
        if not block:
            continue

        header_m = re.match(r"###\s+(.*?)(?:\n|$)", block)
        if not header_m:
            continue

        raw_name = header_m.group(1).strip()
        # Normalize: strip "Requirement N:" or "N." prefix
        name = re.sub(r"^Requirement\s+\d+:\s*", "", raw_name)
        name = re.sub(r"^\d+\.\s*", "", name)
        name = sanitize_name(name)

        # Skip non-requirement subsections (like "### System Components", "### Data Flow")
        # These typically don't have user stories or acceptance criteria
        user_story_m = re.search(
            r"\*\*User Story:\*\*\s*(.*?)(?=\n(?<!#)#{3,4}|\Z)",
            block, re.DOTALL
        )
        # Also detect the multi-line format: "**As a** ... **I want to** ... **So that** ..."
        as_a_m = re.search(
            r"\*\*As an?\*\*\s*(.*?)(?=\n|\*\*)",
            block, re.DOTALL
        )
        i_want_m = re.search(
            r"\*\*I want to\*\*\s*(.*?)(?=\n|\*\*)",
            block, re.DOTALL
        )
        so_that_m = re.search(
            r"\*\*So that\*\*\s*(.*?)(?=\n(?<!#)#{3,4}|\Z)",
            block, re.DOTALL
        )
        has_multi_line_user_story = bool(as_a_m and i_want_m)

        # Also detect bullet-story format: "- **Story**: <narrative>"
        story_m = re.search(
            r"-\s+\*\*Story\*\*:\s*(.*?)(?=\n|\*\*)",
            block, re.DOTALL
        )

        # Match various acceptance criteria formats:
        # - "#### Acceptance Criteria" header
        # - "**Acceptance Criteria:**" bold text
        # - "- **Acceptance Criteria**:" bullet with bold text
        ac_m = re.search(
            r"(?:####\s+Acceptance\s+Criteria|\*\*Acceptance\s+Criteria|-\s+\*\*Acceptance\s+Criteria)\S*\s*\n(.*?)(?=\n(?<!#)###\s+|\Z)",
            block, re.DOTALL
        )

        # Skip blocks that have neither user story nor acceptance criteria
        if not user_story_m and not has_multi_line_user_story and not story_m and not ac_m:
            continue

        if user_story_m:
            req_text = user_story_m.group(1).strip().replace("\n", " ")
            if "SHALL" not in req_text and "MUST" not in req_text:
                req_text = f"The system SHALL support: {req_text}"
        elif has_multi_line_user_story:
            role = as_a_m.group(1).strip()
            goal = i_want_m.group(1).strip()
            benefit = so_that_m.group(1).strip() if so_that_m else ""
            req_text = f"As a {role}, I want to {goal}"
            if benefit:
                req_text += f", so that {benefit}"
            req_text = req_text.replace("\n", " ")
            if "SHALL" not in req_text and "MUST" not in req_text:
                req_text = f"The system SHALL support: {req_text}"
        elif story_m:
            req_text = story_m.group(1).strip().replace("\n", " ")
            if "SHALL" not in req_text and "MUST" not in req_text:
                req_text = f"The system SHALL {req_text}"
        else:
            req_text = f"The system SHALL implement {name.lower()} as described in the requirements."

        if len(req_text) > 500:
            req_text = req_text[:497] + "..."

        # Parse acceptance criteria → scenarios
        scenarios = []
        if ac_m:
            scenarios = parse_acceptance_criteria(ac_m.group(1))
        elif user_story_m:
            # Try inline criteria after user story
            m2 = re.search(
                r"\*\*User Story:\*\*.*?\n(.*?)(?=\n(?<!#)###\s+|\Z)",
                block, re.DOTALL
            )
            if m2:
                scenarios = parse_acceptance_criteria(m2.group(1))

        if not scenarios:
            scenarios = [{
                "name": f"Scenario: {name}",
                "steps": [f"- **THEN** {req_text}"]
            }]

        requirements.append({
            "name": name,
            "text": req_text,
            "scenarios": scenarios
        })

    return requirements


def convert_bugfix_to_requirements(content: str) -> list[dict]:
    """Parse formal bugfix.md (3-part: Current/Expected/Unchanged) into requirements."""
    requirements = []
    scenarios = parse_bugfix_behaviors(content, "expected")
    unchanged = parse_bugfix_behaviors(content, "unchanged")

    title_m = re.search(r"^#\s+(.*)", content, re.MULTILINE)
    title = title_m.group(1) if title_m else "Bugfix"
    title = re.sub(r"^Bugfix Requirements Document$", "Bugfix", title)
    title = re.sub(r"^Bug:\s*", "", title)

    if scenarios:
        requirements.append({
            "name": f"Expected Behavior: {sanitize_name(title)}",
            "text": f"The system SHALL correctly handle {title.lower()} as specified in the expected behavior."[:500],
            "scenarios": scenarios
        })

    if unchanged:
        requirements.append({
            "name": f"Regression Prevention: {sanitize_name(title)}",
            "text": f"The system SHALL CONTINUE TO maintain existing correct behavior for {title.lower()} after the fix."[:500],
            "scenarios": unchanged
        })

    return requirements


def convert_simple_bugfix_to_requirements(content: str) -> list[dict]:
    """Parse simple bugfix.md (no formal Current/Expected/Unchanged sections)."""
    requirements = []
    title_m = re.search(r"^#\s+(.*)", content, re.MULTILINE)
    title = title_m.group(1) if title_m else "Bugfix"

    # Find Expected Behavior sections (## or ### level)
    sections = re.findall(
        r"#{2,3}\s+Expected Behavior\s*\n(.*?)(?=#{2,3}\s+(?:Impact|Bug \d|Root Cause|Summary|$)|\Z)",
        content, re.DOTALL
    )

    for i, section in enumerate(sections):
        text = section.strip()
        req_name = f"Expected Behavior: {sanitize_name(title)}"
        if i > 0:
            req_name += f" (Part {i+1})"

        requirements.append({
            "name": req_name,
            "text": f"The system SHALL {text[:400].strip()}"[:500],
            "scenarios": [{
                "name": f"Scenario: {sanitize_name(title)}",
                "steps": [f"- **THEN** {text[:200].strip()}"]
            }]
        })

    return requirements


def generate_spec_md(purpose: str, requirements: list[dict]) -> str:
    """Generate OpenSpec spec.md content."""
    lines = ["## Purpose", "", purpose, "", "## Requirements", ""]

    for req in requirements:
        lines.append(f"### Requirement: {req['name']}")
        lines.append("")
        lines.append(req["text"])
        lines.append("")
        for scenario in req["scenarios"]:
            lines.append(f"#### {scenario['name']}")
            lines.append("")
            lines.extend(scenario["steps"])
            lines.append("")

    return "\n".join(lines)


def convert_spec_dir(spec_name: str) -> bool:
    """Convert a single Kiro spec directory to OpenSpec."""
    kiro_dir = KIRO_SPECS / spec_name
    openspec_dir = OPENSPEC_SPECS / spec_name

    if not kiro_dir.is_dir():
        return False

    requirements_file = kiro_dir / "requirements.md"
    bugfix_file = kiro_dir / "bugfix.md"
    design_file = kiro_dir / "design.md"
    tasks_file = kiro_dir / "tasks.md"

    has_requirements = requirements_file.exists()
    has_bugfix = bugfix_file.exists()
    has_design = design_file.exists()
    has_tasks = tasks_file.exists()

    if not has_requirements and not has_bugfix and not has_design and not has_tasks:
        print(f"  SKIP (empty): {spec_name}")
        return False

    openspec_dir.mkdir(parents=True, exist_ok=True)

    if has_requirements:
        content = requirements_file.read_text(encoding="utf-8")
        purpose = extract_purpose_from_requirements(content)
        requirements = parse_requirements_section(content)
        print(f"  CONVERT (requirements): {spec_name} → {len(requirements)} requirements")
    elif has_bugfix:
        content = bugfix_file.read_text(encoding="utf-8")
        purpose = extract_purpose_from_bugfix(content)
        is_formal = (
            "### Current Behavior" in content
            and "### Expected Behavior" in content
            and "### Unchanged Behavior" in content
        )
        if is_formal:
            requirements = convert_bugfix_to_requirements(content)
        else:
            requirements = convert_simple_bugfix_to_requirements(content)
        print(f"  CONVERT (bugfix): {spec_name} → {len(requirements)} requirements")
    else:
        purpose = f"This capability covers the {spec_name.replace('-', ' ')} implementation. See design.md for technical details."
        requirements = [{
            "name": sanitize_name(spec_name.replace("-", " ").title()),
            "text": f"The system SHALL implement {spec_name.replace('-', ' ')} as described in the design document.",
            "scenarios": [{
                "name": f"Scenario: {spec_name.replace('-', ' ')}",
                "steps": [f"- **THEN** the system SHALL function according to the design specification."]
            }]
        }]
        print(f"  CONVERT (stub): {spec_name}")

    spec_file = openspec_dir / "spec.md"
    spec_file.write_text(generate_spec_md(purpose, requirements), encoding="utf-8")

    if has_design:
        shutil.copy2(str(design_file), str(openspec_dir / "design.md"))
    if has_tasks:
        shutil.copy2(str(tasks_file), str(openspec_dir / "tasks.md"))

    return True


def main():
    print("=" * 60)
    print("Kiro → OpenSpec Conversion")
    print("=" * 60)

    OPENSPEC_SPECS.mkdir(parents=True, exist_ok=True)

    spec_dirs = sorted([
        d.name for d in KIRO_SPECS.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ])

    print(f"\nFound {len(spec_dirs)} spec directories in .kiro/specs/")
    print(f"Output: {OPENSPEC_SPECS}\n")

    converted, skipped = 0, 0
    for name in spec_dirs:
        if convert_spec_dir(name):
            converted += 1
        else:
            skipped += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {converted} converted, {skipped} skipped")
    print(f"Output directory: {OPENSPEC_SPECS}")
    print("=" * 60)


if __name__ == "__main__":
    main()
