from __future__ import annotations

import ast
import json
import re
import textwrap

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from discord.ext import commands
from openai import AsyncOpenAI

from utils.checks import is_gm


DEFAULT_MODEL = "gpt-5.3-codex"
DEFAULT_REASONING_EFFORT = "medium"
DEFAULT_MAX_SNIPPETS = 6
DEFAULT_MAX_CONTEXT_CHARS = 16000
DEFAULT_MAX_OUTPUT_TOKENS = 700
MAX_FILE_BYTES = 1000000
WINDOW_SIZE = 40
WINDOW_OVERLAP = 10
BASE_MAX_FOLLOW_BLOCKS = 16
FOLLOW_QUEUE_MULTIPLIER = 6
FOLLOW_SEED_COUNT = 2
FOLLOW_MIN_SYMBOL_SCORE = 24.0
MAX_PYTHON_BLOCK_LINES = 80
MAX_PYTHON_BLOCK_EXCERPTS = 2
MAX_JSON_BLOCK_LINES = 80
MAX_MARKDOWN_SECTION_LINES = 100
MAX_SQL_STATEMENT_LINES = 140
SOURCE_EXTENSIONS = {".py", ".md", ".json", ".toml", ".sql"}
ROOT_SOURCE_FILES = {"README.md", "config.py", "idlerpg.py", "launcher.py"}
SOURCE_DIRS = {"cogs", "classes", "utils", "scripts", "tests"}
EXCLUDED_SOURCE_PATHS = {
    "cogs/chatgpt/__init__.py",
    "tests/test_chatgpt_repo_context.py",
}
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "bot",
    "can",
    "code",
    "command",
    "commands",
    "describe",
    "does",
    "do",
    "for",
    "from",
    "game",
    "give",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "player",
    "players",
    "question",
    "questions",
    "repo",
    "tell",
    "the",
    "this",
    "to",
    "what",
    "work",
    "works",
    "why",
    "with",
}
SHORT_QUERY_TERMS = {"ai", "gm", "hp", "jt", "mp", "sp", "ui", "xp"}
TECHNICAL_HINTS = {
    "attribute",
    "cite",
    "cites",
    "citation",
    "citations",
    "class",
    "code",
    "coder",
    "coders",
    "developer",
    "developers",
    "dev",
    "debug",
    "excerpt",
    "excerpts",
    "file",
    "files",
    "flag",
    "function",
    "implementation",
    "implemented",
    "internally",
    "line",
    "lines",
    "logic",
    "method",
    "proof",
    "prove",
    "reference",
    "references",
    "runtime",
    "show source",
    "show sources",
    "show code",
    "source",
    "sources",
    "technical",
    "technically",
    "variable",
}
BASE_SYSTEM_INSTRUCTIONS = (
    "You answer questions about the FableReborn Discord bot codebase. "
    "Use only the supplied repository excerpts. "
    "When the excerpts include exact values, names, thresholds, or formulas, state them directly. "
    "If the excerpts are not enough, say that clearly. "
    "Do not claim to have inspected files that were not included in the prompt."
)
TERM_SYNONYMS = {
    "cbt": ("couples", "couples_battletower", "battletower", "tower"),
    "couples": ("cbt", "couples_battletower", "battletower", "tower"),
    "battletower": ("battle", "tower"),
    "rank": ("ranking", "ranks", "bracket", "score", "tier"),
    "ranking": ("rank", "ranks", "bracket", "score", "tier"),
    "ranks": ("rank", "ranking", "bracket", "score", "tier"),
    "score": ("rank", "ranking", "bracket", "tier"),
    "bracket": ("rank", "ranking", "score", "tier"),
    "tier": ("rank", "ranking", "bracket", "score"),
    "prestige": ("cycle", "cycles", "reset"),
    "cycles": ("cycle", "prestige"),
    "checkpoint": ("boss", "progress"),
}


@dataclass(frozen=True)
class RankedSnippet:
    path: str
    start_line: int
    end_line: int
    score: float
    text: str

    @property
    def reference(self) -> str:
        return f"{self.path}:{self.start_line}-{self.end_line}"


PYTHON_DEF_RE = re.compile(r"^(\s*)(?:async\s+def|def)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
PYTHON_CLASS_RE = re.compile(r"^(\s*)class\s+([A-Za-z_][A-Za-z0-9_]*)\b")
FOLLOW_CALL_RE = re.compile(r"self\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")
CONSTANT_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")
SELF_ASSIGN_RE = re.compile(r"self\.([A-Za-z_][A-Za-z0-9_]*)\s*=")
FILE_REFERENCE_RE = re.compile(
    r"['\"]([^'\"]+\.(?:py|json|toml|sql|md))['\"]",
    re.IGNORECASE,
)
MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
STRUCTURED_QUERY_TARGET_RE = re.compile(
    r"\b(level|levels|floor|floors|stage|stages|reward|rewards|victory|victories|dialogue|dialogues)\s+(\d+)\b"
)
FOLLOW_IGNORE_SYMBOLS = {
    "bool",
    "dict",
    "float",
    "int",
    "len",
    "list",
    "max",
    "min",
    "print",
    "round",
    "set",
    "str",
    "sum",
    "tuple",
}
LOW_SIGNAL_SYMBOL_TOKENS = {
    "build",
    "clip",
    "create",
    "data",
    "ensure",
    "format",
    "guard",
    "help",
    "info",
    "load",
    "normalize",
    "preview",
    "progress",
    "render",
    "save",
    "shop",
    "start",
}
HIGH_SIGNAL_SYMBOL_TOKENS = {
    "apply",
    "attack",
    "battle",
    "bonus",
    "bracket",
    "calculate",
    "chance",
    "cooldown",
    "damage",
    "effect",
    "fight",
    "logic",
    "multiplier",
    "payload",
    "prestige",
    "process",
    "rank",
    "ranking",
    "resolve",
    "result",
    "reward",
    "score",
    "snapshot",
    "state",
    "update",
}
PythonSymbolBlock = tuple[str, int, int, str]


def _normalize_repo_path(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _iter_source_dir_paths(repo_root: Path, directory_name: str) -> list[Path]:
    base_path = repo_root / directory_name
    if not base_path.exists():
        return []

    results: list[Path] = []
    for path in base_path.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        results.append(path)
    return results


def iter_repo_source_paths(repo_root: Path) -> list[Path]:
    repo_root = Path(repo_root)
    results: list[Path] = []

    for file_name in sorted(ROOT_SOURCE_FILES):
        path = repo_root / file_name
        if (
            path.is_file()
            and path.stat().st_size <= MAX_FILE_BYTES
            and _normalize_repo_path(path, repo_root) not in EXCLUDED_SOURCE_PATHS
        ):
            results.append(path)

    for directory_name in sorted(SOURCE_DIRS):
        results.extend(
            sorted(
                path
                for path in _iter_source_dir_paths(repo_root, directory_name)
                if _normalize_repo_path(path, repo_root) not in EXCLUDED_SOURCE_PATHS
            )
        )

    return results


def extract_query_terms(question: str) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []

    for raw_token in re.findall(r"[a-zA-Z0-9_./-]+", question.casefold()):
        for token in re.split(r"[_./-]+", raw_token):
            for variant in _expand_query_term_variants(token):
                if variant.isdigit():
                    if len(variant) > 4:
                        continue
                elif len(variant) < 3 and variant not in SHORT_QUERY_TERMS:
                    continue
                if (
                    variant in STOP_WORDS
                ):
                    continue
                if variant not in seen:
                    seen.add(variant)
                    terms.append(variant)

    return terms


def _expand_query_term_variants(token: str) -> list[str]:
    normalized = token.casefold().strip()
    if not normalized:
        return []

    variants = [normalized]
    if normalized.endswith("ing") and len(normalized) > 5:
        variants.append(normalized[:-3])
    if normalized.endswith("ed") and len(normalized) > 4:
        variants.append(normalized[:-2])
    if normalized.endswith("es") and len(normalized) > 4:
        variants.append(normalized[:-2])
    if normalized.endswith("s") and len(normalized) > 4:
        variants.append(normalized[:-1])
    variants.extend(TERM_SYNONYMS.get(normalized, ()))

    deduped: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        if variant and variant not in seen:
            seen.add(variant)
            deduped.append(variant)
    return deduped


def extract_query_phrases(question: str) -> list[str]:
    seen: set[str] = set()
    phrases: list[str] = []

    for phrase in re.findall(r'"([^"]+)"|\'([^\']+)\'', question):
        value = (phrase[0] or phrase[1]).strip()
        normalized = " ".join(value.casefold().split())
        if len(normalized) >= 3 and normalized not in seen:
            seen.add(normalized)
            phrases.append(normalized)

    title_case_pattern = re.compile(r"\b(?:[A-Z][A-Za-z0-9']+\s+){1,}[A-Z][A-Za-z0-9']+\b")
    for match in title_case_pattern.finditer(question):
        normalized = " ".join(match.group(0).casefold().split())
        if normalized not in seen:
            seen.add(normalized)
            phrases.append(normalized)

    snake_case_pattern = re.compile(r"\b[a-z0-9]+(?:_[a-z0-9]+)+\b", re.IGNORECASE)
    for match in snake_case_pattern.finditer(question):
        normalized = match.group(0).casefold().replace("_", " ")
        if normalized not in seen:
            seen.add(normalized)
            phrases.append(normalized)

    return phrases


def _phrase_forms(phrase: str) -> set[str]:
    words = tuple(word for word in phrase.casefold().split() if word)
    if not words:
        return set()
    return {
        " ".join(words),
        "_".join(words),
        "-".join(words),
    }


def _count_term_occurrences(text: str, term: str) -> int:
    if not term:
        return 0
    if term.isdigit():
        return len(re.findall(rf"(?<!\d){re.escape(term)}(?!\d)", text))
    return text.count(term)


def _path_priority_score(path_text: str, question_lower: str) -> float:
    score = 0.0
    path_lower = path_text.casefold()
    if path_text.startswith(("cogs/", "classes/", "utils/")):
        score += 6
    if path_text.startswith("tests/") and "test" not in question_lower and "tests" not in question_lower:
        score -= 260
    if path_text.startswith("tools/") and "tool" not in question_lower and "audit" not in question_lower:
        score -= 90
    if path_text.startswith(("assets/", "locales/")):
        score -= 10
    if re.search(r"\b(schema|schemas|table|tables|column|columns|field|fields|database|sql)\b", question_lower):
        if path_lower.endswith(".sql"):
            score += 85
        if "schema" in path_lower:
            score += 55
    if re.search(r"\b(level|levels|floor|floors|stage)\b", question_lower):
        if "levels" in path_lower:
            score += 55
        elif path_lower.endswith("_data.json") or path_lower.endswith("_data_remastered.json"):
            score -= 20
    if re.search(r"\b(dialogue|dialogues|quote|quotes|say|says|said)\b", question_lower):
        if "dialogue" in path_lower:
            score += 55
    if re.search(r"\b(reward|rewards|chest|loot|drop|drops|victory|victories)\b", question_lower):
        if "data" in path_lower or "reward" in path_lower:
            score += 40
    return score


def _extract_structured_query_targets(question_lower: str) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    family_aliases = {
        "level": "levels",
        "levels": "levels",
        "floor": "floors",
        "floors": "floors",
        "stage": "stages",
        "stages": "stages",
        "reward": "rewards",
        "rewards": "rewards",
        "victory": "victories",
        "victories": "victories",
        "dialogue": "dialogues",
        "dialogues": "dialogues",
    }
    for family, value in STRUCTURED_QUERY_TARGET_RE.findall(question_lower):
        normalized_target = (family_aliases[family], value)
        if normalized_target in seen:
            continue
        seen.add(normalized_target)
        targets.append(normalized_target)
    return targets


def _extract_structured_path_label(text: str) -> str | None:
    first_line = text.splitlines()[0].strip() if text else ""
    if not first_line.startswith("JSON path: "):
        return None
    return first_line[len("JSON path: ") :].strip() or None


def _score_json_path_label(question_lower: str, label: str | None) -> float:
    if not label:
        return 0.0

    score = 0.0
    label_lower = label.casefold()
    targets = _extract_structured_query_targets(question_lower)
    if not targets:
        return score

    numeric_labels = set(re.findall(r"\[(\d+)\]", label_lower))
    for family, numeric_value in targets:
        if not label_lower.startswith(family):
            continue
        if f"[{numeric_value}]" in label_lower:
            score += 220
            continue
        if numeric_labels and numeric_value not in numeric_labels:
            score -= 90
    return score


def _extract_sql_table_targets(terms: list[str], phrases: list[str]) -> list[str]:
    schema_terms = {
        "schema",
        "schemas",
        "table",
        "tables",
        "column",
        "columns",
        "field",
        "fields",
        "database",
        "sql",
        "what",
        "which",
        "show",
        "list",
        "there",
        "are",
        "the",
        "in",
        "of",
    }
    seen: set[str] = set()
    targets: list[str] = []

    for phrase in phrases:
        normalized = phrase.casefold().replace(" ", "_")
        if not normalized or normalized in schema_terms or normalized in seen:
            continue
        seen.add(normalized)
        targets.append(normalized)

    for term in terms:
        if term in schema_terms or term.isdigit() or term in seen:
            continue
        seen.add(term)
        targets.append(term)

    return targets


def _score_symbol_name(symbol_name: str | None, terms: list[str], phrases: list[str]) -> float:
    if not symbol_name:
        return 0.0

    normalized = symbol_name.casefold().replace("_", " ")
    symbol_tokens = set(re.findall(r"[a-z0-9]+", normalized))
    term_set = set(terms)
    score = 0.0
    for phrase in phrases:
        if any(form in normalized for form in _phrase_forms(phrase)):
            score += 42
    for term in terms:
        if term in normalized:
            score += 12
    for token in HIGH_SIGNAL_SYMBOL_TOKENS:
        if token in symbol_tokens:
            score += 14
    for token in LOW_SIGNAL_SYMBOL_TOKENS:
        if token in symbol_tokens and token not in term_set:
            score -= 24
    if symbol_tokens.intersection(LOW_SIGNAL_SYMBOL_TOKENS) and not symbol_tokens.intersection(HIGH_SIGNAL_SYMBOL_TOKENS):
        score -= 40
    return score


def _is_follow_worthy_symbol(symbol_name: str | None, terms: list[str], phrases: list[str]) -> bool:
    if not symbol_name:
        return False

    normalized = symbol_name.casefold().replace("_", " ")
    symbol_tokens = set(re.findall(r"[a-z0-9]+", normalized))
    if symbol_tokens.intersection(LOW_SIGNAL_SYMBOL_TOKENS) and not symbol_tokens.intersection(HIGH_SIGNAL_SYMBOL_TOKENS):
        return False

    return _score_symbol_name(symbol_name, terms, phrases) >= FOLLOW_MIN_SYMBOL_SCORE


def _score_text_block(
    question: str,
    terms: list[str],
    phrases: list[str],
    path_text: str,
    text: str,
) -> float:
    question_lower = question.casefold().strip()
    path_lower = path_text.casefold()
    text_lower = text.casefold()

    if not terms and not phrases and not question_lower:
        return 0.0

    score = 0.0
    matched_terms = 0

    for phrase in phrases:
        for form in _phrase_forms(phrase):
            if form in path_lower:
                score += 45
            if form in text_lower:
                score += 90

    if question_lower and question_lower in path_lower:
        score += 45
    if question_lower and question_lower in text_lower:
        score += 35

    for term in terms:
        path_hits = _count_term_occurrences(path_lower, term)
        text_hits = _count_term_occurrences(text_lower, term)
        if path_hits or text_hits:
            matched_terms += 1
        if path_hits:
            score += 8 + min(path_hits, 4) * 5
        if text_hits:
            score += min(text_hits, 10) * 2

    score += (matched_terms * 4) + (matched_terms * matched_terms * 4)
    score += _path_priority_score(path_text, question_lower)
    return score


def _score_json_block(
    question: str,
    terms: list[str],
    phrases: list[str],
    path_text: str,
    text: str,
) -> float:
    score = _score_text_block(question, terms, phrases, path_text, text)
    question_lower = question.casefold()
    text_lower = text.casefold()
    term_set = set(terms)
    numeric_terms = [term for term in terms if term.isdigit()]
    score += _score_json_path_label(question_lower, _extract_structured_path_label(text))

    if term_set.intersection({"level", "levels"}):
        if "levels" in path_text.casefold():
            score += 35
        for term in numeric_terms:
            if re.search(rf'"level"\s*:\s*{re.escape(term)}\b', text_lower):
                score += 130
            elif re.search(rf'"{re.escape(term)}"\s*:', text_lower):
                score += 30

    if term_set.intersection({"floor", "floors"}):
        for term in numeric_terms:
            if re.search(rf'"floor"\s*:\s*{re.escape(term)}\b', text_lower):
                score += 130
            elif re.search(rf'"{re.escape(term)}"\s*:', text_lower):
                score += 30

    if term_set.intersection({"dialogue", "dialogues"}):
        if '"dialogue' in text_lower or '"speaker"' in text_lower:
            score += 70

    if term_set.intersection({"reward", "rewards", "chest", "loot", "drop", "drops", "victory", "victories"}):
        if '"reward' in text_lower or '"chest' in text_lower or '"victor' in text_lower:
            score += 70

    if term_set.intersection({"enemy", "enemies", "boss", "minion"}):
        if '"enemies"' in text_lower or '"boss"' in text_lower or '"minion' in text_lower:
            score += 55

    return score


def _score_sql_block(
    question: str,
    terms: list[str],
    phrases: list[str],
    path_text: str,
    text: str,
) -> float:
    score = _score_text_block(question, terms, phrases, path_text, text)
    question_lower = question.casefold()
    text_lower = text.casefold()
    term_set = set(terms)
    table_targets = _extract_sql_table_targets(terms, phrases)
    schema_question = bool(
        term_set.intersection({"schema", "schemas", "table", "tables", "column", "columns", "field", "fields", "database", "sql"})
    )
    matched_table_target = False

    if path_text.casefold().endswith(".sql"):
        score += 35

    if schema_question and not table_targets:
        if path_text.casefold().endswith(".sql"):
            score += 70
        if "create table" in text_lower:
            score += 45
        if "alter table" in text_lower:
            score += 20

    for table_name in table_targets:
        create_pattern = rf"\bcreate\s+table(?:\s+if\s+not\s+exists)?\s+{re.escape(table_name)}\b"
        alter_pattern = rf"\balter\s+table\s+{re.escape(table_name)}\b"
        if re.search(create_pattern, text_lower):
            matched_table_target = True
            score += 210
            if schema_question:
                score += 60
        elif re.search(alter_pattern, text_lower):
            matched_table_target = True
            score += 120
        elif re.search(rf"\b{re.escape(table_name)}\b", text_lower):
            matched_table_target = True
            score += 35

    if schema_question and table_targets:
        if matched_table_target:
            if path_text.casefold().endswith(".sql"):
                score += 70
            if "create table" in text_lower:
                score += 45
            if "alter table" in text_lower:
                score += 20
        else:
            score -= 180

    if term_set.intersection({"column", "columns", "field", "fields"}) and (matched_table_target or not table_targets):
        column_lines = 0
        for line in text_lower.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("--", "/*", "create table", "alter table", "constraint", "primary key", "unique", "foreign key", ");")):
                continue
            if re.match(r"^[a-z_][a-z0-9_]*\s+[a-z]", stripped):
                column_lines += 1
        if column_lines:
            score += min(column_lines, 12) * 18

    return score


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _iter_line_windows(text: str, window_size: int = WINDOW_SIZE) -> Iterable[tuple[int, int, str]]:
    lines = text.splitlines()
    if not lines:
        return

    step = max(1, window_size - WINDOW_OVERLAP)
    for start_index in range(0, len(lines), step):
        window = lines[start_index : start_index + window_size]
        if not window:
            break
        start_line = start_index + 1
        end_line = start_index + len(window)
        yield start_line, end_line, "\n".join(window)
        if end_line >= len(lines):
            break


def _line_matches_query(line_text: str, terms: list[str], phrases: list[str]) -> bool:
    line_lower = line_text.casefold()
    for phrase in phrases:
        if any(form in line_lower for form in _phrase_forms(phrase)):
            return True
    for term in terms:
        if _count_term_occurrences(line_lower, term):
            return True
    return False


def _iter_targeted_windows(
    text: str,
    terms: list[str],
    phrases: list[str],
    window_size: int = WINDOW_SIZE,
) -> Iterable[tuple[int, int, str]]:
    lines = text.splitlines()
    if not lines:
        return

    seen_ranges: set[tuple[int, int]] = set()
    half_window = max(1, window_size // 2)
    for index, line in enumerate(lines):
        if not _line_matches_query(line, terms, phrases):
            continue
        start_index = max(0, index - half_window)
        end_index = min(len(lines), start_index + window_size)
        window = lines[start_index:end_index]
        range_key = (start_index, end_index)
        if not window or range_key in seen_ranges:
            continue
        if any(start_index < seen_end and end_index > seen_start for seen_start, seen_end in seen_ranges):
            continue
        seen_ranges.add(range_key)
        yield start_index + 1, end_index, "\n".join(window)


def _iter_python_blocks(text: str) -> Iterable[tuple[int, int, str, str]]:
    lines = text.splitlines()
    if not lines:
        return

    boundaries: list[tuple[int, int, str | None, str]] = []
    decorator_start: int | None = None

    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("@"):
            if decorator_start is None:
                decorator_start = index
            continue

        match = PYTHON_DEF_RE.match(line)
        if match:
            indent = len(match.group(1))
            start_index = decorator_start if decorator_start is not None else index
            boundaries.append((start_index, indent, match.group(2), "def"))
            decorator_start = None
            continue

        class_match = PYTHON_CLASS_RE.match(line)
        if class_match:
            indent = len(class_match.group(1))
            boundaries.append((index, indent, None, "class"))
            decorator_start = None
            continue

        if stripped and not stripped.startswith("#"):
            decorator_start = None

    def_boundaries = [boundary for boundary in boundaries if boundary[3] == "def"]

    for position, (start_index, indent, symbol_name, _) in enumerate(def_boundaries):
        end_index = len(lines)
        for next_start, next_indent, _, _ in boundaries:
            if next_start <= start_index:
                continue
            if next_indent <= indent:
                end_index = next_start
                break
        block_lines = lines[start_index:end_index]
        if block_lines:
            yield start_index + 1, end_index, "\n".join(block_lines), symbol_name


def _extract_self_assigned_symbols(block_text: str) -> list[str]:
    seen: set[str] = set()
    symbols: list[str] = []
    for match in SELF_ASSIGN_RE.finditer(block_text):
        symbol_name = match.group(1)
        if len(symbol_name) < 3 or symbol_name in seen:
            continue
        seen.add(symbol_name)
        symbols.append(symbol_name)
    return symbols


def _iter_python_named_value_blocks(text: str) -> Iterable[tuple[int, int, str, str]]:
    lines = text.splitlines()
    if not lines:
        return

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return

    for node in tree.body:
        target_names: list[str] = []
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    target_names.append(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_names.append(node.target.id)

        if not target_names:
            continue

        for symbol_name in target_names:
            if len(symbol_name) < 3 or not CONSTANT_SYMBOL_RE.match(symbol_name):
                continue
            start_line = getattr(node, "lineno", None)
            end_line = getattr(node, "end_lineno", start_line)
            if not start_line or not end_line:
                continue
            block_lines = lines[start_line - 1 : end_line]
            if block_lines:
                yield start_line, end_line, "\n".join(block_lines), symbol_name


def _module_parts_to_source_path(repo_root: Path, module_parts: list[str]) -> str | None:
    if not module_parts:
        return None

    module_path = repo_root.joinpath(*module_parts)
    candidate_files = [
        module_path.with_suffix(".py"),
        module_path / "__init__.py",
    ]
    for candidate in candidate_files:
        if candidate.is_file():
            return _normalize_repo_path(candidate, repo_root)
    return None


def _resolve_imported_module_path(repo_root: Path, path_text: str, module_name: str | None, level: int) -> str | None:
    current_parts = list(Path(path_text).with_suffix("").parts[:-1])
    if level > 0:
        keep_count = max(0, len(current_parts) - (level - 1))
        module_parts = current_parts[:keep_count]
        if module_name:
            module_parts.extend(part for part in module_name.split(".") if part)
        return _module_parts_to_source_path(repo_root, module_parts)

    if not module_name:
        return None
    return _module_parts_to_source_path(repo_root, [part for part in module_name.split(".") if part])


def _extract_python_imported_symbol_paths(
    text: str,
    *,
    repo_root: Path,
    path_text: str,
) -> dict[str, str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}

    imported_symbols: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        source_path = _resolve_imported_module_path(repo_root, path_text, node.module, node.level)
        if not source_path:
            continue
        for alias in node.names:
            local_name = alias.asname or alias.name
            if not local_name or local_name == "*":
                continue
            imported_symbols[local_name] = source_path

    return imported_symbols


def _extract_file_reference_paths(text: str) -> list[str]:
    seen: set[str] = set()
    references: list[str] = []
    for match in FILE_REFERENCE_RE.finditer(text):
        reference = match.group(1).replace("\\", "/").lstrip("./")
        if not reference or reference in seen:
            continue
        seen.add(reference)
        references.append(reference)
    return references


def _json_brace_delta(line_text: str) -> int:
    delta = 0
    in_string = False
    escaped = False

    for char in line_text:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char in "{[":
            delta += 1
        elif char in "}]":
            delta -= 1
    return delta


def _find_json_object_bounds(lines: list[str], index: int) -> tuple[int, int] | None:
    start_index = index
    while start_index >= 0:
        candidate = lines[start_index].strip()
        if candidate == "{" or candidate.endswith("{"):
            break
        start_index -= 1
    if start_index < 0:
        return None

    balance = 0
    end_index = start_index
    started = False
    while end_index < len(lines):
        balance += _json_brace_delta(lines[end_index])
        if "{" in lines[end_index] or "[" in lines[end_index]:
            started = True
        if started and balance <= 0:
            break
        end_index += 1

    end_index = min(end_index, len(lines) - 1)
    return start_index, end_index


def _json_path_label(path_parts: tuple[str, ...]) -> str:
    if not path_parts:
        return "root"

    parts: list[str] = []
    for part in path_parts:
        if part.startswith("[") and parts:
            parts[-1] = f"{parts[-1]}{part}"
        else:
            parts.append(part)
    return ".".join(parts)


def _iter_json_candidate_nodes(
    node,
    *,
    path_parts: tuple[str, ...] = (),
) -> Iterable[tuple[str, object]]:
    if isinstance(node, dict):
        if path_parts and (
            path_parts[-1].isdigit()
            or any(key in node for key in ("level", "floor", "title", "story", "dialogue_start", "description", "rewards", "chest_rewards"))
        ):
            yield _json_path_label(path_parts), node

        for key, value in node.items():
            next_parts = path_parts + (str(key),)
            if isinstance(value, dict):
                yield from _iter_json_candidate_nodes(value, path_parts=next_parts)
            elif isinstance(value, list):
                if key in {"levels", "floors", "victories", "dialogues", "rewards", "stages"}:
                    for index, item in enumerate(value, start=1):
                        if not isinstance(item, (dict, list)):
                            continue
                        list_label = str(item.get("level") or item.get("floor") or index) if isinstance(item, dict) else str(index)
                        yield from _iter_json_candidate_nodes(item, path_parts=next_parts + (f"[{list_label}]",))
                elif value and all(not isinstance(item, (dict, list)) for item in value[:8]):
                    yield _json_path_label(next_parts), value
                else:
                    for index, item in enumerate(value, start=1):
                        if isinstance(item, (dict, list)):
                            yield from _iter_json_candidate_nodes(item, path_parts=next_parts + (f"[{index}]",))
        return

    if isinstance(node, list) and path_parts:
        yield _json_path_label(path_parts), node


def _json_anchor_patterns(label: str, node) -> list[str]:
    patterns: list[str] = []
    if isinstance(node, dict):
        if "level" in node and isinstance(node["level"], (int, float, str)):
            patterns.append(rf'"level"\s*:\s*{re.escape(str(node["level"]))}(?!\d)')
        if "floor" in node and isinstance(node["floor"], (int, float, str)):
            patterns.append(rf'"floor"\s*:\s*{re.escape(str(node["floor"]))}(?!\d)')
        if "title" in node and isinstance(node["title"], str) and node["title"].strip():
            patterns.append(re.escape(node["title"].strip()[:80]))
        if "name" in node and isinstance(node["name"], str) and node["name"].strip():
            patterns.append(re.escape(node["name"].strip()[:80]))
        if "dialogue_start" in node and isinstance(node["dialogue_start"], str) and node["dialogue_start"].strip():
            patterns.append(re.escape(node["dialogue_start"].strip()[:80]))
    tail = label.rsplit(".", 1)[-1]
    numeric_match = re.fullmatch(r"(?:\[(\d+)\]|(\d+))", tail)
    if numeric_match:
        numeric_key = numeric_match.group(1) or numeric_match.group(2)
        patterns.append(rf'"{re.escape(numeric_key)}"\s*:\s*\{{')
    return patterns


def _find_json_anchor_bounds(text: str, label: str, node) -> tuple[int, int] | None:
    lines = text.splitlines()
    if not lines:
        return None

    for pattern in _json_anchor_patterns(label, node):
        compiled = re.compile(pattern, re.IGNORECASE)
        for index, line in enumerate(lines):
            if not compiled.search(line):
                continue
            bounds = _find_json_object_bounds(lines, index)
            if not bounds:
                continue
            start_index, end_index = bounds
            if (end_index - start_index + 1) > MAX_JSON_BLOCK_LINES:
                continue
            return start_index + 1, end_index + 1

    return None


def _iter_json_structured_windows(
    text: str,
    terms: list[str],
    phrases: list[str],
) -> Iterable[tuple[int, int, str]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return

    seen_ranges: set[tuple[int, int]] = set()
    for label, node in _iter_json_candidate_nodes(data):
        rendered = json.dumps(node, indent=2, ensure_ascii=True)
        rendered_with_label = f"JSON path: {label}\n{rendered}"
        if not _line_matches_query(label, terms, phrases) and not _line_matches_query(rendered_with_label, terms, phrases):
            continue
        bounds = _find_json_anchor_bounds(text, label, node)
        if not bounds:
            continue
        range_key = (bounds[0], bounds[1])
        if range_key in seen_ranges:
            continue
        seen_ranges.add(range_key)
        yield bounds[0], bounds[1], rendered_with_label


def _iter_markdown_sections(
    text: str,
    terms: list[str],
    phrases: list[str],
) -> Iterable[tuple[int, int, str]]:
    lines = text.splitlines()
    if not lines:
        return

    headings: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = MARKDOWN_HEADING_RE.match(line)
        if not match:
            continue
        headings.append((index, match.group(2).strip()))

    if not headings:
        return

    for position, (start_index, heading_text) in enumerate(headings):
        end_index = headings[position + 1][0] - 1 if position + 1 < len(headings) else len(lines) - 1
        section_lines = lines[start_index : end_index + 1]
        if not section_lines:
            continue
        section_text = "\n".join(section_lines)
        labeled_text = f"Markdown section: {heading_text}\n{section_text}"
        if not _line_matches_query(labeled_text, terms, phrases):
            continue
        if len(section_lines) > MAX_MARKDOWN_SECTION_LINES:
            limited_lines = section_lines[:MAX_MARKDOWN_SECTION_LINES]
            section_text = "\n".join(limited_lines)
            end_index = start_index + len(limited_lines) - 1
            labeled_text = f"Markdown section: {heading_text}\n{section_text}"
        yield start_index + 1, end_index + 1, labeled_text


def _iter_sql_statements(
    text: str,
    terms: list[str],
    phrases: list[str],
) -> Iterable[tuple[int, int, str]]:
    lines = text.splitlines()
    if not lines:
        return

    buffer: list[str] = []
    start_line: int | None = None
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if start_line is None and not stripped:
            continue
        if start_line is None:
            start_line = index
        buffer.append(line)
        if stripped.endswith(";"):
            statement_text = "\n".join(buffer).strip()
            if statement_text:
                labeled_text = statement_text
                if _line_matches_query(labeled_text, terms, phrases):
                    statement_lines = statement_text.splitlines()
                    end_line = start_line + len(statement_lines) - 1
                    if len(statement_lines) > MAX_SQL_STATEMENT_LINES:
                        statement_lines = statement_lines[:MAX_SQL_STATEMENT_LINES]
                        end_line = start_line + len(statement_lines) - 1
                    yield start_line, end_line, "\n".join(statement_lines)
            buffer = []
            start_line = None

    if buffer and start_line is not None:
        statement_text = "\n".join(buffer).strip()
        if statement_text and _line_matches_query(statement_text, terms, phrases):
            statement_lines = statement_text.splitlines()
            end_line = start_line + len(statement_lines) - 1
            if len(statement_lines) > MAX_SQL_STATEMENT_LINES:
                statement_lines = statement_lines[:MAX_SQL_STATEMENT_LINES]
                end_line = start_line + len(statement_lines) - 1
            yield start_line, end_line, "\n".join(statement_lines)


def _iter_json_target_blocks(
    text: str,
    terms: list[str],
) -> Iterable[tuple[int, int, str]]:
    lines = text.splitlines()
    if not lines:
        return

    numeric_terms = [term for term in terms if term.isdigit()]
    if not numeric_terms:
        return

    seen_ranges: set[tuple[int, int]] = set()
    for index, line in enumerate(lines):
        line_lower = line.casefold()
        if not any(
            re.search(rf'"\w+"\s*:\s*{re.escape(term)}\b', line_lower)
            or re.search(rf'"{re.escape(term)}"\s*:', line_lower)
            for term in numeric_terms
        ):
            continue

        start_index = index
        while start_index > 0:
            candidate = lines[start_index].strip()
            if candidate == "{" or candidate.endswith("{"):
                break
            start_index -= 1

        balance = 0
        end_index = start_index
        started = False
        while end_index < len(lines):
            balance += _json_brace_delta(lines[end_index])
            if "{" in lines[end_index] or "[" in lines[end_index]:
                started = True
            if started and balance <= 0:
                break
            end_index += 1

        range_key = (start_index, min(end_index, len(lines) - 1))
        if range_key in seen_ranges:
            continue
        if (range_key[1] - range_key[0] + 1) > MAX_JSON_BLOCK_LINES:
            continue
        seen_ranges.add(range_key)
        yield (
            start_index + 1,
            range_key[1] + 1,
            "\n".join(lines[range_key[0] : range_key[1] + 1]),
        )


def _iter_json_object_windows(
    text: str,
    terms: list[str],
    phrases: list[str],
) -> Iterable[tuple[int, int, str]]:
    lines = text.splitlines()
    if not lines:
        return

    seen_ranges: set[tuple[int, int]] = set()
    for index, line in enumerate(lines):
        if not _line_matches_query(line, terms, phrases):
            continue
        bounds = _find_json_object_bounds(lines, index)
        if not bounds:
            continue
        start_index, end_index = bounds
        range_key = (start_index, end_index)
        if range_key in seen_ranges:
            continue
        if (end_index - start_index + 1) > MAX_JSON_BLOCK_LINES:
            continue
        seen_ranges.add(range_key)
        yield start_index + 1, end_index + 1, "\n".join(lines[start_index : end_index + 1])


def _resolve_file_reference_path(
    reference: str,
    *,
    source_path: str | None,
    repo_paths_by_basename: dict[str, list[str]],
    source_text_by_path: dict[str, str],
) -> str | None:
    normalized = reference.replace("\\", "/").lstrip("./")
    if normalized in source_text_by_path:
        return normalized

    basename = Path(normalized).name
    matches = repo_paths_by_basename.get(basename, [])
    if len(matches) == 1:
        return matches[0]

    if source_path and "/" in normalized:
        base_parts = list(Path(source_path).parts[:-1])
        candidate_parts = list(Path(normalized).parts)
        while base_parts:
            candidate = Path(*base_parts, *candidate_parts).as_posix()
            if candidate in source_text_by_path:
                return candidate
            base_parts.pop()

    return None


def _build_follow_file_snippets(
    path_text: str,
    text: str,
    *,
    question: str,
    terms: list[str],
    phrases: list[str],
    seen_refs: set[tuple[str, int, int]],
    limit: int = 2,
) -> list[RankedSnippet]:
    candidates: list[RankedSnippet] = []
    used_structured_json = False
    used_structured_text = False
    if path_text.endswith(".json"):
        for start_line, end_line, window_text in _iter_json_structured_windows(text, terms, phrases):
            ref = (path_text, start_line, end_line)
            if ref in seen_refs:
                continue
            score = _score_json_block(question, terms, phrases, path_text, window_text) + 110
            if score <= 0:
                continue
            candidates.append(
                RankedSnippet(
                    path=path_text,
                    start_line=start_line,
                    end_line=end_line,
                    score=score,
                    text=window_text.strip(),
                )
            )
            used_structured_json = True
        for start_line, end_line, window_text in _iter_json_object_windows(text, terms, phrases):
            ref = (path_text, start_line, end_line)
            if ref in seen_refs:
                continue
            score = _score_json_block(question, terms, phrases, path_text, window_text) + 45
            if score <= 0:
                continue
            candidates.append(
                RankedSnippet(
                    path=path_text,
                    start_line=start_line,
                    end_line=end_line,
                    score=score,
                    text=window_text.strip(),
                )
            )
            used_structured_json = True
        for start_line, end_line, window_text in _iter_json_target_blocks(text, terms):
            ref = (path_text, start_line, end_line)
            if ref in seen_refs:
                continue
            score = _score_json_block(question, terms, phrases, path_text, window_text) + 70
            if score <= 0:
                continue
            candidates.append(
                RankedSnippet(
                    path=path_text,
                    start_line=start_line,
                    end_line=end_line,
                    score=score,
                    text=window_text.strip(),
                )
            )
            used_structured_json = True
    elif path_text.endswith(".md"):
        for start_line, end_line, window_text in _iter_markdown_sections(text, terms, phrases):
            ref = (path_text, start_line, end_line)
            if ref in seen_refs:
                continue
            score = _score_text_block(question, terms, phrases, path_text, window_text) + 55
            if score <= 0:
                continue
            candidates.append(
                RankedSnippet(
                    path=path_text,
                    start_line=start_line,
                    end_line=end_line,
                    score=score,
                    text=window_text.strip(),
                )
            )
            used_structured_text = True
    elif path_text.endswith(".sql"):
        for start_line, end_line, window_text in _iter_sql_statements(text, terms, phrases):
            ref = (path_text, start_line, end_line)
            if ref in seen_refs:
                continue
            score = _score_sql_block(question, terms, phrases, path_text, window_text) + 55
            if score <= 0:
                continue
            candidates.append(
                RankedSnippet(
                    path=path_text,
                    start_line=start_line,
                    end_line=end_line,
                    score=score,
                    text=window_text.strip(),
                )
            )
            used_structured_text = True

    if not ((path_text.endswith(".json") and used_structured_json) or used_structured_text):
        for start_line, end_line, window_text in _iter_targeted_windows(text, terms, phrases):
            ref = (path_text, start_line, end_line)
            if ref in seen_refs:
                continue
            score = (
                _score_json_block(question, terms, phrases, path_text, window_text)
                if path_text.endswith(".json")
                else _score_sql_block(question, terms, phrases, path_text, window_text)
                if path_text.endswith(".sql")
                else _score_text_block(question, terms, phrases, path_text, window_text)
            )
            if score <= 0:
                continue
            candidates.append(
                RankedSnippet(
                    path=path_text,
                    start_line=start_line,
                    end_line=end_line,
                    score=score,
                    text=window_text.strip(),
                )
            )

        for start_line, end_line, window_text in _iter_line_windows(text):
            ref = (path_text, start_line, end_line)
            if ref in seen_refs:
                continue
            score = (
                _score_json_block(question, terms, phrases, path_text, window_text)
                if path_text.endswith(".json")
                else _score_sql_block(question, terms, phrases, path_text, window_text)
                if path_text.endswith(".sql")
                else _score_text_block(question, terms, phrases, path_text, window_text)
            )
            if score <= 0:
                continue
            candidates.append(
                RankedSnippet(
                    path=path_text,
                    start_line=start_line,
                    end_line=end_line,
                    score=score,
                    text=window_text.strip(),
                )
            )

    selected: list[RankedSnippet] = []
    for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
        if any(
            candidate.start_line <= existing.end_line and candidate.end_line >= existing.start_line
            for existing in selected
        ):
            continue
        selected.append(candidate)
        if len(selected) >= limit:
            break
    return selected


def _iter_python_block_excerpt_windows(
    block_start_line: int,
    block_text: str,
    terms: list[str],
    phrases: list[str],
) -> Iterable[tuple[int, int, str]]:
    lines = block_text.splitlines()
    if not lines:
        return

    if len(lines) <= MAX_PYTHON_BLOCK_LINES:
        yield block_start_line, block_start_line + len(lines) - 1, block_text
        return

    targeted_windows = list(
        _iter_targeted_windows(
            block_text,
            terms,
            phrases,
            window_size=MAX_PYTHON_BLOCK_LINES,
        )
    )
    if targeted_windows:
        for rel_start, rel_end, window_text in targeted_windows[:MAX_PYTHON_BLOCK_EXCERPTS]:
            yield (
                block_start_line + rel_start - 1,
                block_start_line + rel_end - 1,
                window_text,
            )
        return

    excerpt_lines = lines[:MAX_PYTHON_BLOCK_LINES]
    yield (
        block_start_line,
        block_start_line + len(excerpt_lines) - 1,
        "\n".join(excerpt_lines),
    )


def _extract_follow_symbols_from_text(text: str) -> list[str]:
    normalized_text = textwrap.dedent(text)
    symbols: list[str] = []
    seen: set[str] = set()

    try:
        tree = ast.parse(normalized_text)
    except SyntaxError:
        for match in FOLLOW_CALL_RE.finditer(text):
            symbol_name = match.group(1)
            if symbol_name in FOLLOW_IGNORE_SYMBOLS or symbol_name in seen:
                continue
            seen.add(symbol_name)
            symbols.append(symbol_name)
        for match in re.finditer(r"self\.([A-Za-z_][A-Za-z0-9_]*)\b", text):
            symbol_name = match.group(1)
            if len(symbol_name) < 3 or symbol_name in seen:
                continue
            seen.add(symbol_name)
            symbols.append(symbol_name)
        for symbol_name in re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", text):
            if symbol_name in seen:
                continue
            seen.add(symbol_name)
            symbols.append(symbol_name)
        return symbols

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            symbol_name = None
            if isinstance(node.func, ast.Name):
                symbol_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                symbol_name = node.func.attr

            if not symbol_name:
                continue
            if len(symbol_name) < 3 or symbol_name in FOLLOW_IGNORE_SYMBOLS:
                continue
            if symbol_name in seen:
                continue
            seen.add(symbol_name)
            symbols.append(symbol_name)
            continue

        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            symbol_name = node.id
            if not CONSTANT_SYMBOL_RE.match(symbol_name):
                continue
            if symbol_name in seen:
                continue
            seen.add(symbol_name)
            symbols.append(symbol_name)
            continue

        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        ):
            symbol_name = node.attr
            if len(symbol_name) < 3 or symbol_name in seen:
                continue
            seen.add(symbol_name)
            symbols.append(symbol_name)

    return symbols


def _resolve_symbol_blocks(
    symbol_name: str,
    *,
    source_path: str | None,
    python_symbol_defs: dict[str, list[PythonSymbolBlock]],
    python_symbol_defs_by_path: dict[str, dict[str, list[PythonSymbolBlock]]],
    python_imported_symbol_paths: dict[str, dict[str, str]],
) -> list[PythonSymbolBlock]:
    if source_path:
        local_defs = python_symbol_defs_by_path.get(source_path, {}).get(symbol_name, [])
        if local_defs:
            return local_defs

        imported_path = python_imported_symbol_paths.get(source_path, {}).get(symbol_name)
        if imported_path:
            imported_defs = python_symbol_defs_by_path.get(imported_path, {}).get(symbol_name, [])
            if imported_defs:
                return imported_defs

    return python_symbol_defs.get(symbol_name, [])


def _looks_like_named_value_snippet(snippet: RankedSnippet) -> bool:
    first_line = snippet.text.splitlines()[0].strip() if snippet.text else ""
    if not first_line or "=" not in first_line:
        return False
    candidate_name = first_line.split("=", 1)[0].strip()
    if not CONSTANT_SYMBOL_RE.match(candidate_name):
        return False
    return ("\n" in snippet.text) or any(token in snippet.text for token in ("{", "[", "("))


def _collect_follow_snippets(
    snippets: list[RankedSnippet],
    python_symbol_defs: dict[str, list[PythonSymbolBlock]],
    python_symbol_defs_by_path: dict[str, dict[str, list[PythonSymbolBlock]]],
    python_imported_symbol_paths: dict[str, dict[str, str]],
    source_text_by_path: dict[str, str],
    repo_paths_by_basename: dict[str, list[str]],
    *,
    question: str,
    terms: list[str],
    phrases: list[str],
    max_follow_blocks: int,
) -> list[RankedSnippet]:
    follow_candidates: list[RankedSnippet] = []
    seen_symbols: set[str] = set()
    seen_refs = {
        (snippet.path, snippet.start_line, snippet.end_line)
        for snippet in snippets
    }
    queue: list[tuple[float, str, int, str | None]] = []
    max_queue_pops = max_follow_blocks * FOLLOW_QUEUE_MULTIPLIER
    queue_pops = 0

    seed_snippets = snippets[: min(FOLLOW_SEED_COUNT, len(snippets))]
    for snippet in seed_snippets:
        for symbol_name in _extract_follow_symbols_from_text(snippet.text):
            if symbol_name in seen_symbols:
                continue
            if not _is_follow_worthy_symbol(symbol_name, terms, phrases):
                continue
            queue.append((snippet.score, symbol_name, 0, snippet.path))

    while queue and len(follow_candidates) < max_follow_blocks and queue_pops < max_queue_pops:
        queue.sort(key=lambda item: item[0], reverse=True)
        parent_priority, symbol_name, depth, source_path = queue.pop(0)
        queue_pops += 1
        if symbol_name in seen_symbols:
            continue
        seen_symbols.add(symbol_name)

        blocks = _resolve_symbol_blocks(
            symbol_name,
            source_path=source_path,
            python_symbol_defs=python_symbol_defs,
            python_symbol_defs_by_path=python_symbol_defs_by_path,
            python_imported_symbol_paths=python_imported_symbol_paths,
        )
        if not blocks:
            continue

        for path_text, start_line, end_line, block_text in blocks:
            best_excerpt = None
            best_excerpt_relevance = 0.0
            for excerpt_start, excerpt_end, excerpt_text in _iter_python_block_excerpt_windows(
                start_line,
                block_text,
                terms,
                phrases,
            ):
                ref = (path_text, excerpt_start, excerpt_end)
                if ref in seen_refs:
                    continue
                excerpt_relevance = (
                    _score_text_block(question, terms, phrases, path_text, excerpt_text)
                    + _score_symbol_name(symbol_name, terms, phrases)
                )
                if excerpt_relevance > best_excerpt_relevance:
                    best_excerpt_relevance = excerpt_relevance
                    best_excerpt = (excerpt_start, excerpt_end, excerpt_text)

            if best_excerpt is None or best_excerpt_relevance <= 0:
                continue
            excerpt_start, excerpt_end, excerpt_text = best_excerpt
            follow_score = (
                best_excerpt_relevance
                + min(80.0, parent_priority * 0.15)
                - min(depth * 14, 70)
            )
            follow_candidates.append(
                RankedSnippet(
                    path=path_text,
                    start_line=excerpt_start,
                    end_line=excerpt_end,
                    score=follow_score,
                    text=excerpt_text.strip(),
                )
            )
            seen_refs.add((path_text, excerpt_start, excerpt_end))

            for reference in _extract_file_reference_paths(block_text):
                resolved_path = _resolve_file_reference_path(
                    reference,
                    source_path=path_text,
                    repo_paths_by_basename=repo_paths_by_basename,
                    source_text_by_path=source_text_by_path,
                )
                if not resolved_path:
                    continue
                file_text = source_text_by_path.get(resolved_path)
                if not file_text:
                    continue
                for file_snippet in _build_follow_file_snippets(
                    resolved_path,
                    file_text,
                    question=question,
                    terms=terms,
                    phrases=phrases,
                    seen_refs=seen_refs,
                    limit=2,
                ):
                    follow_candidates.append(
                        RankedSnippet(
                            path=file_snippet.path,
                            start_line=file_snippet.start_line,
                            end_line=file_snippet.end_line,
                            score=file_snippet.score + min(70.0, follow_score * 0.12),
                            text=file_snippet.text,
                        )
                    )
                    seen_refs.add(
                        (file_snippet.path, file_snippet.start_line, file_snippet.end_line)
                    )
                    if len(follow_candidates) >= max_follow_blocks:
                        break
                if len(follow_candidates) >= max_follow_blocks:
                    break

            for nested_symbol in _extract_follow_symbols_from_text(block_text):
                if nested_symbol in seen_symbols:
                    continue
                if not _is_follow_worthy_symbol(nested_symbol, terms, phrases):
                    continue
                nested_priority = max(20.0, follow_score * 0.85)
                queue.append((nested_priority, nested_symbol, depth + 1, path_text))

            if len(follow_candidates) >= max_follow_blocks:
                break

    return follow_candidates


def _select_ranked_snippets(
    snippet_candidates: list[RankedSnippet],
    *,
    max_snippets: int,
    max_context_chars: int,
    max_per_path: int | None = None,
) -> list[RankedSnippet]:
    selected: list[RankedSnippet] = []
    total_chars = 0
    seen_refs: set[tuple[str, int, int]] = set()
    path_counts: dict[str, int] = {}
    ordered_candidates = sorted(snippet_candidates, key=lambda item: item.score, reverse=True)
    if not ordered_candidates:
        return []
    min_score_threshold = max(60.0, ordered_candidates[0].score * 0.22)

    for snippet in ordered_candidates:
        if len(selected) >= max_snippets:
            break
        if not snippet.text:
            continue
        if snippet.score < min_score_threshold:
            continue
        ref = (snippet.path, snippet.start_line, snippet.end_line)
        if ref in seen_refs:
            continue
        if max_per_path is not None and path_counts.get(snippet.path, 0) >= max_per_path:
            continue
        projected_total = total_chars + len(snippet.text)
        if selected and projected_total > max_context_chars:
            continue
        seen_refs.add(ref)
        path_counts[snippet.path] = path_counts.get(snippet.path, 0) + 1
        total_chars = projected_total
        selected.append(snippet)

    return selected


def _assemble_context_snippets(
    primary_snippets: list[RankedSnippet],
    follow_snippets: list[RankedSnippet],
    anchor_snippets: list[RankedSnippet],
    snippet_candidates: list[RankedSnippet],
    *,
    max_snippets: int,
    max_context_chars: int,
) -> list[RankedSnippet]:
    selected: list[RankedSnippet] = []
    seen_refs: set[tuple[str, int, int]] = set()
    total_chars = 0
    path_counts: dict[str, int] = {}

    def try_add(snippet: RankedSnippet, *, path_cap: int | None = None) -> bool:
        nonlocal total_chars

        if len(selected) >= max_snippets or not snippet.text:
            return False

        ref = (snippet.path, snippet.start_line, snippet.end_line)
        if ref in seen_refs:
            return False
        if path_cap is not None and path_counts.get(snippet.path, 0) >= path_cap:
            return False

        projected_total = total_chars + len(snippet.text)
        if selected and projected_total > max_context_chars:
            return False

        seen_refs.add(ref)
        path_counts[snippet.path] = path_counts.get(snippet.path, 0) + 1
        total_chars = projected_total
        selected.append(snippet)
        return True

    if primary_snippets:
        try_add(primary_snippets[0], path_cap=4)
    for snippet in primary_snippets[1:]:
        if len(selected) >= max_snippets:
            break
        if not _looks_like_named_value_snippet(snippet):
            continue
        try_add(snippet, path_cap=1)

    ordered_follow = sorted(follow_snippets, key=lambda item: item.score, reverse=True)
    follow_added = 0
    if primary_snippets and ordered_follow:
        primary_score = primary_snippets[0].score
        top_follow_score = ordered_follow[0].score
        follow_threshold = max(45.0, primary_score * 0.25, top_follow_score * 0.4)
        follow_quota = max(3, max_snippets // 2)
        for snippet in ordered_follow:
            if follow_added >= follow_quota or len(selected) >= max_snippets:
                break
            if snippet.score < follow_threshold:
                continue
            if try_add(snippet, path_cap=4):
                follow_added += 1

    if follow_added >= 2 and len(selected) >= min(max_snippets, 3):
        return selected

    for snippet in anchor_snippets:
        if len(selected) >= max_snippets:
            break
        try_add(snippet, path_cap=1)

    fill_threshold = 0.0
    if primary_snippets:
        fill_threshold = max(60.0, primary_snippets[0].score * 0.25)
    for snippet in sorted(snippet_candidates, key=lambda item: item.score, reverse=True):
        if len(selected) >= max_snippets:
            break
        if fill_threshold and snippet.score < fill_threshold:
            break
        try_add(snippet, path_cap=2)

    return selected


def build_repo_context(
    question: str,
    repo_root: Path,
    *,
    max_snippets: int = DEFAULT_MAX_SNIPPETS,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
) -> list[RankedSnippet]:
    repo_root = Path(repo_root)
    terms = extract_query_terms(question)
    phrases = extract_query_phrases(question)
    file_candidates: list[tuple[float, Path, str]] = []
    python_symbol_defs: dict[str, list[PythonSymbolBlock]] = {}
    python_symbol_defs_by_path: dict[str, dict[str, list[PythonSymbolBlock]]] = {}
    python_imported_symbol_paths: dict[str, dict[str, str]] = {}
    source_text_by_path: dict[str, str] = {}
    repo_paths_by_basename: dict[str, list[str]] = {}

    for path in iter_repo_source_paths(repo_root):
        try:
            text = _read_text(path)
        except OSError:
            continue

        if not text.strip():
            continue

        path_text = _normalize_repo_path(path, repo_root)
        source_text_by_path[path_text] = text
        repo_paths_by_basename.setdefault(path.name, []).append(path_text)
        if path.suffix.lower() == ".py":
            python_imported_symbol_paths[path_text] = _extract_python_imported_symbol_paths(
                text,
                repo_root=repo_root,
                path_text=path_text,
            )
            path_symbol_defs = python_symbol_defs_by_path.setdefault(path_text, {})
            for start_line, end_line, block_text, symbol_name in _iter_python_blocks(text):
                block = (path_text, start_line, end_line, block_text)
                python_symbol_defs.setdefault(symbol_name, []).append(block)
                path_symbol_defs.setdefault(symbol_name, []).append(block)
                for assigned_symbol in _extract_self_assigned_symbols(block_text):
                    python_symbol_defs.setdefault(assigned_symbol, []).append(block)
                    path_symbol_defs.setdefault(assigned_symbol, []).append(block)
            for start_line, end_line, block_text, symbol_name in _iter_python_named_value_blocks(text):
                block = (path_text, start_line, end_line, block_text)
                python_symbol_defs.setdefault(symbol_name, []).append(block)
                path_symbol_defs.setdefault(symbol_name, []).append(block)

        file_score = (
            _score_json_block(question, terms, phrases, path_text, text)
            if path.suffix.lower() == ".json"
            else _score_sql_block(question, terms, phrases, path_text, text)
            if path.suffix.lower() == ".sql"
            else _score_text_block(question, terms, phrases, path_text, text)
        )
        if file_score <= 0:
            continue

        file_candidates.append((file_score, path, text))

    if not file_candidates:
        return []

    snippet_candidates: list[RankedSnippet] = []
    for file_score, path, text in sorted(file_candidates, key=lambda item: item[0], reverse=True)[:12]:
        path_text = _normalize_repo_path(path, repo_root)
        best_for_file: list[RankedSnippet] = []
        candidate_windows: list[tuple[int, int, str, str | None]] = []
        seen_window_refs: set[tuple[int, int]] = set()
        has_structured_json_windows = False
        has_structured_text_windows = False

        if path.suffix.lower() == ".py":
            for symbol_name, entries in python_symbol_defs_by_path.get(path_text, {}).items():
                for _, start_line, end_line, block_text in entries:
                    block_score = (
                        _score_text_block(question, terms, phrases, path_text, block_text)
                        + _score_symbol_name(symbol_name, terms, phrases)
                    )
                    if block_score <= 0:
                        continue
                    for excerpt_start, excerpt_end, excerpt_text in _iter_python_block_excerpt_windows(
                        start_line,
                        block_text,
                        terms,
                        phrases,
                    ):
                        if (excerpt_start, excerpt_end) in seen_window_refs:
                            continue
                        candidate_windows.append((excerpt_start, excerpt_end, excerpt_text, symbol_name))
                        seen_window_refs.add((excerpt_start, excerpt_end))
        elif path.suffix.lower() == ".json":
            for start_line, end_line, window_text in _iter_json_structured_windows(text, terms, phrases):
                if (start_line, end_line) in seen_window_refs:
                    continue
                candidate_windows.append((start_line, end_line, window_text, None))
                seen_window_refs.add((start_line, end_line))
                has_structured_json_windows = True
            for start_line, end_line, window_text in _iter_json_object_windows(text, terms, phrases):
                if (start_line, end_line) in seen_window_refs:
                    continue
                candidate_windows.append((start_line, end_line, window_text, None))
                seen_window_refs.add((start_line, end_line))
                has_structured_json_windows = True
            for start_line, end_line, window_text in _iter_json_target_blocks(text, terms):
                if (start_line, end_line) in seen_window_refs:
                    continue
                candidate_windows.append((start_line, end_line, window_text, None))
                seen_window_refs.add((start_line, end_line))
                has_structured_json_windows = True
        elif path.suffix.lower() == ".md":
            for start_line, end_line, window_text in _iter_markdown_sections(text, terms, phrases):
                if (start_line, end_line) in seen_window_refs:
                    continue
                candidate_windows.append((start_line, end_line, window_text, None))
                seen_window_refs.add((start_line, end_line))
                has_structured_text_windows = True
        elif path.suffix.lower() == ".sql":
            for start_line, end_line, window_text in _iter_sql_statements(text, terms, phrases):
                if (start_line, end_line) in seen_window_refs:
                    continue
                candidate_windows.append((start_line, end_line, window_text, None))
                seen_window_refs.add((start_line, end_line))
                has_structured_text_windows = True

        if not (
            (path.suffix.lower() == ".json" and has_structured_json_windows)
            or has_structured_text_windows
        ):
            targeted_windows = list(_iter_targeted_windows(text, terms, phrases))
            for start_line, end_line, window_text in targeted_windows:
                if (start_line, end_line) in seen_window_refs:
                    continue
                candidate_windows.append((start_line, end_line, window_text, None))
                seen_window_refs.add((start_line, end_line))

            for start_line, end_line, window_text in _iter_line_windows(text):
                if (start_line, end_line) in seen_window_refs:
                    continue
                candidate_windows.append((start_line, end_line, window_text, None))
                seen_window_refs.add((start_line, end_line))

        for start_line, end_line, window_text, symbol_name in candidate_windows:
            base_score = (
                _score_json_block(question, terms, phrases, path_text, window_text)
                if path.suffix.lower() == ".json"
                else _score_sql_block(question, terms, phrases, path_text, window_text)
                if path.suffix.lower() == ".sql"
                else _score_text_block(question, terms, phrases, path_text, window_text)
            )
            window_score = base_score + _score_symbol_name(symbol_name, terms, phrases) + (file_score * 0.15)
            if window_score <= 0:
                continue
            best_for_file.append(
                RankedSnippet(
                    path=path_text,
                    start_line=start_line,
                    end_line=end_line,
                    score=window_score,
                    text=window_text.strip(),
                )
            )

        if best_for_file:
            file_snippets: list[RankedSnippet] = []
            for candidate in sorted(best_for_file, key=lambda item: item.score, reverse=True):
                if any(
                    candidate.start_line <= existing.end_line and candidate.end_line >= existing.start_line
                    for existing in file_snippets
                ):
                    continue
                file_snippets.append(candidate)
                if len(file_snippets) >= 3:
                    break
            snippet_candidates.extend(file_snippets)
        else:
            snippet_candidates.append(
                RankedSnippet(
                    path=path_text,
                    start_line=1,
                    end_line=min(len(text.splitlines()), WINDOW_SIZE),
                    score=file_score,
                    text="\n".join(text.splitlines()[:WINDOW_SIZE]).strip(),
                )
            )

    primary_snippets = _select_ranked_snippets(
        snippet_candidates,
        max_snippets=FOLLOW_SEED_COUNT,
        max_context_chars=max_context_chars,
    )
    anchor_snippets = _select_ranked_snippets(
        snippet_candidates,
        max_snippets=max(max_snippets, 4),
        max_context_chars=max_context_chars,
        max_per_path=1,
    )
    follow_snippets = _collect_follow_snippets(
        primary_snippets,
        python_symbol_defs,
        python_symbol_defs_by_path,
        python_imported_symbol_paths,
        source_text_by_path,
        repo_paths_by_basename,
        question=question,
        terms=terms,
        phrases=phrases,
        max_follow_blocks=max(BASE_MAX_FOLLOW_BLOCKS, max_snippets * 4),
    )
    return _assemble_context_snippets(
        primary_snippets,
        follow_snippets,
        anchor_snippets,
        snippet_candidates,
        max_snippets=max_snippets,
        max_context_chars=max_context_chars,
    )


def format_repo_context(snippets: list[RankedSnippet]) -> str:
    parts: list[str] = []
    for snippet in snippets:
        language = Path(snippet.path).suffix.lstrip(".") or "text"
        parts.append(
            f"[{snippet.reference}]\n```{language}\n{snippet.text}\n```"
        )
    return "\n\n".join(parts)


def extract_response_text(response) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text_value = getattr(content, "text", None)
            if isinstance(text_value, str) and text_value.strip():
                parts.append(text_value.strip())
                continue
            value = getattr(text_value, "value", None)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())

    return "\n".join(parts).strip()


def split_for_discord(text: str, limit: int = 1900) -> list[str]:
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n\n", 0, limit)
        if split_at == -1:
            split_at = remaining.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at == -1:
            split_at = limit
        chunk = remaining[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def wants_technical_answer(question: str) -> bool:
    question_lower = question.casefold()
    return any(hint in question_lower for hint in TECHNICAL_HINTS)


def build_system_instructions(question: str) -> str:
    if wants_technical_answer(question):
        return (
            f"{BASE_SYSTEM_INSTRUCTIONS} "
            "Answer for a technical reader. "
            "Include concrete implementation details when useful. "
            "Cite concrete claims with bracketed references like "
            "[cogs/raidbuilder/__init__.py:120-160]."
        )

    return (
        f"{BASE_SYSTEM_INSTRUCTIONS} "
        "Default to a non-technical, player-facing explanation in plain English. "
        "Focus on what the feature does in practice, not internal implementation details. "
        "Avoid code terms, variable names, file paths, and citations unless the user explicitly asks for them. "
        "Keep the answer natural and easy to read."
    )


class ChatGPTCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.repo_root = Path(__file__).resolve().parents[2]
        self.settings = self._load_settings()
        self.model = self.settings.get("model", DEFAULT_MODEL)
        self.reasoning_effort = self.settings.get("reasoning_effort", DEFAULT_REASONING_EFFORT)
        self.max_snippets = int(self.settings.get("max_snippets", DEFAULT_MAX_SNIPPETS))
        self.max_context_chars = int(self.settings.get("max_context_chars", DEFAULT_MAX_CONTEXT_CHARS))
        self.max_output_tokens = int(self.settings.get("max_output_tokens", DEFAULT_MAX_OUTPUT_TOKENS))
        openai_key = getattr(self.bot.config.external, "openai", None)
        self.client = AsyncOpenAI(api_key=openai_key) if openai_key else None

    def _load_settings(self) -> dict:
        ids_section = getattr(self.bot.config, "ids", None)
        if ids_section is None:
            return {}
        settings = getattr(ids_section, "chatgpt", {})
        return settings if isinstance(settings, dict) else {}

    async def _ask_openai(self, question: str, snippets: list[RankedSnippet]) -> str:
        if self.client is None:
            raise RuntimeError("Missing OpenAI API key in config.toml under [external].openai.")

        prompt = (
            f"User question:\n{question.strip()}\n\n"
            "Repository excerpts:\n"
            f"{format_repo_context(snippets)}\n\n"
            "Answer the question using the excerpts only."
        )
        response = await self.client.responses.create(
            model=self.model,
            instructions=build_system_instructions(question),
            input=prompt,
            max_output_tokens=self.max_output_tokens,
            reasoning={"effort": self.reasoning_effort},
            truncation="auto",
        )
        answer = extract_response_text(response)
        if answer:
            return answer
        raise RuntimeError("OpenAI returned an empty response.")

    async def _send_answer(
        self,
        ctx,
        answer: str,
        snippets: list[RankedSnippet],
        *,
        include_sources: bool,
    ) -> None:
        mention = ctx.author.mention
        sources = "Sources: " + ", ".join(f"`{snippet.reference}`" for snippet in snippets)
        message_parts = split_for_discord(answer)
        if not message_parts:
            await ctx.send(f"{mention} I couldn't produce an answer from the selected repo context.")
            return

        single_message = f"{mention} {message_parts[0]}"
        if len(message_parts) == 1 and (
            not include_sources or len(single_message) + len(sources) + 2 <= 1900
        ):
            if include_sources:
                await ctx.send(f"{single_message}\n\n{sources}")
            else:
                await ctx.send(single_message)
            return

        await ctx.send(f"{mention} {message_parts[0]}")
        for part in message_parts[1:]:
            await ctx.send(part)
        if include_sources:
            await ctx.send(sources)

    @commands.command(
        name="askme",
        aliases=["codex", "askcode", "repoai"],
        hidden=True,
        brief="Ask the GM-only repo assistant a codebase question.",
    )
    @commands.cooldown(1, 15, commands.BucketType.user)
    @is_gm()
    async def askme(self, ctx, *, question: str):
        """Ask a repo-aware coding assistant about the bot codebase."""
        await ctx.send(
            f"{ctx.author.mention} It might take a few moments to get a response, "
            "but I'll ping you when it's ready."
        )
        async with ctx.typing():
            snippets = build_repo_context(
                question,
                self.repo_root,
                max_snippets=self.max_snippets,
                max_context_chars=self.max_context_chars,
            )
            if not snippets:
                await ctx.send(
                    f"{ctx.author.mention} I couldn't find relevant repo snippets for that question. "
                    "Try naming a file, command, class, or feature more directly."
                )
                return

            try:
                answer = await self._ask_openai(question, snippets)
            except Exception as exc:
                self.bot.logger.error(f"Codex command failed: {exc}")
                await ctx.send(f"{ctx.author.mention} Codex request failed: {exc}")
                return

        await self._send_answer(
            ctx,
            answer,
            snippets,
            include_sources=wants_technical_answer(question),
        )


async def setup(bot):
    await bot.add_cog(ChatGPTCog(bot))
