from __future__ import annotations

import asyncio
import json

from pathlib import Path

from .models import RunState


class SpireStorage:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _run_path(self, user_id: int) -> Path:
        return self.root / f"{int(user_id)}.json"

    async def load_run(self, user_id: int) -> RunState | None:
        path = self._run_path(user_id)
        if not path.exists():
            return None
        async with self._lock:
            raw = await asyncio.to_thread(path.read_text, encoding="utf-8")
        return RunState.from_dict(json.loads(raw))

    async def save_run(self, run: RunState) -> None:
        path = self._run_path(run.user_id)
        payload = json.dumps(run.to_dict(), indent=2, sort_keys=True)
        async with self._lock:
            await asyncio.to_thread(path.write_text, payload, encoding="utf-8")

    async def delete_run(self, user_id: int) -> None:
        path = self._run_path(user_id)
        if not path.exists():
            return
        async with self._lock:
            await asyncio.to_thread(path.unlink)
