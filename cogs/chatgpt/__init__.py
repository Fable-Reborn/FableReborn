from __future__ import annotations

import re

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
MAX_FILE_BYTES = 180000
WINDOW_SIZE = 40
WINDOW_OVERLAP = 10
SOURCE_EXTENSIONS = {".py", ".md", ".json", ".toml", ".sql"}
ROOT_SOURCE_FILES = {"README.md", "config.py", "idlerpg.py", "launcher.py"}
SOURCE_DIRS = {"cogs", "classes", "utils", "scripts", "tests"}
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
    "does",
    "for",
    "from",
    "game",
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
    "the",
    "this",
    "to",
    "what",
    "why",
    "with",
}
SYSTEM_INSTRUCTIONS = (
    "You answer questions about the FableReborn Discord bot codebase. "
    "Use only the supplied repository excerpts. "
    "If the excerpts are not enough, say that clearly. "
    "Be concise, practical, and cite concrete claims with bracketed references like "
    "[cogs/raidbuilder/__init__.py:120-160]. "
    "Do not claim to have inspected files that were not included in the prompt."
)


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
        if path.is_file() and path.stat().st_size <= MAX_FILE_BYTES:
            results.append(path)

    for directory_name in sorted(SOURCE_DIRS):
        results.extend(sorted(_iter_source_dir_paths(repo_root, directory_name)))

    return results


def extract_query_terms(question: str) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []

    for raw_token in re.findall(r"[a-zA-Z0-9_./-]+", question.casefold()):
        for token in re.split(r"[_./-]+", raw_token):
            if len(token) < 2 or token.isdigit() or token in STOP_WORDS:
                continue
            if token not in seen:
                seen.add(token)
                terms.append(token)

    return terms


def _score_text_block(question: str, terms: list[str], path_text: str, text: str) -> float:
    question_lower = question.casefold().strip()
    path_lower = path_text.casefold()
    text_lower = text.casefold()

    if not terms and not question_lower:
        return 0.0

    score = 0.0
    matched_terms = 0

    if question_lower and question_lower in path_lower:
        score += 45
    if question_lower and question_lower in text_lower:
        score += 35

    for term in terms:
        path_hits = path_lower.count(term)
        text_hits = text_lower.count(term)
        if path_hits or text_hits:
            matched_terms += 1
        if path_hits:
            score += 8 + min(path_hits, 4) * 5
        if text_hits:
            score += min(text_hits, 10) * 2

    score += matched_terms * 4
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


def build_repo_context(
    question: str,
    repo_root: Path,
    *,
    max_snippets: int = DEFAULT_MAX_SNIPPETS,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
) -> list[RankedSnippet]:
    repo_root = Path(repo_root)
    terms = extract_query_terms(question)
    file_candidates: list[tuple[float, Path, str]] = []

    for path in iter_repo_source_paths(repo_root):
        try:
            text = _read_text(path)
        except OSError:
            continue

        if not text.strip():
            continue

        path_text = _normalize_repo_path(path, repo_root)
        file_score = _score_text_block(question, terms, path_text, text)
        if file_score <= 0:
            continue

        file_candidates.append((file_score, path, text))

    if not file_candidates:
        return []

    snippet_candidates: list[RankedSnippet] = []
    for file_score, path, text in sorted(file_candidates, key=lambda item: item[0], reverse=True)[:12]:
        path_text = _normalize_repo_path(path, repo_root)
        best_for_file: list[RankedSnippet] = []

        for start_line, end_line, window_text in _iter_line_windows(text):
            window_score = _score_text_block(question, terms, path_text, window_text) + (file_score * 0.15)
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
            snippet_candidates.extend(sorted(best_for_file, key=lambda item: item.score, reverse=True)[:2])
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

    selected: list[RankedSnippet] = []
    total_chars = 0
    seen_refs: set[tuple[str, int, int]] = set()

    for snippet in sorted(snippet_candidates, key=lambda item: item.score, reverse=True):
        if len(selected) >= max_snippets:
            break
        if not snippet.text:
            continue
        ref = (snippet.path, snippet.start_line, snippet.end_line)
        if ref in seen_refs:
            continue
        projected_total = total_chars + len(snippet.text)
        if selected and projected_total > max_context_chars:
            continue
        seen_refs.add(ref)
        total_chars = projected_total
        selected.append(snippet)

    return selected


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
            "Answer the question using the excerpts only. Cite claims with the provided file references."
        )
        response = await self.client.responses.create(
            model=self.model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=prompt,
            max_output_tokens=self.max_output_tokens,
            reasoning={"effort": self.reasoning_effort},
            truncation="auto",
        )
        answer = extract_response_text(response)
        if answer:
            return answer
        raise RuntimeError("OpenAI returned an empty response.")

    async def _send_answer(self, ctx, answer: str, snippets: list[RankedSnippet]) -> None:
        mention = ctx.author.mention
        sources = "Sources: " + ", ".join(f"`{snippet.reference}`" for snippet in snippets)
        message_parts = split_for_discord(answer)
        if not message_parts:
            await ctx.send(f"{mention} I couldn't produce an answer from the selected repo context.")
            return

        single_message = f"{mention} {message_parts[0]}"
        if len(message_parts) == 1 and len(single_message) + len(sources) + 2 <= 1900:
            await ctx.send(f"{single_message}\n\n{sources}")
            return

        await ctx.send(f"{mention} {message_parts[0]}")
        for part in message_parts[1:]:
            await ctx.send(part)
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

        await self._send_answer(ctx, answer, snippets)


async def setup(bot):
    await bot.add_cog(ChatGPTCog(bot))
