#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_NAME = "heartbeat_watchdog_config.json"


def _configure_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    return logging.getLogger("heartbeat_watchdog")


def _default_bot_dir(script_dir: Path) -> Path | None:
    parent = script_dir.parent
    if (parent / "launcher.py").is_file():
        return parent
    return None


def _prompt(question: str, default: str | None = None) -> str:
    if default is None:
        prompt = f"{question}: "
    else:
        prompt = f"{question} [{default}]: "
    value = input(prompt).strip()
    if value == "" and default is not None:
        return default
    return value


def _create_config_interactive(config_path: Path, logger: logging.Logger) -> dict[str, Any]:
    if not sys.stdin.isatty():
        raise RuntimeError(
            f"Config missing at {config_path} and no TTY available for setup."
        )

    logger.info("No config found. Running first-time setup.")
    script_dir = config_path.parent
    default_bot_dir = _default_bot_dir(script_dir)
    while True:
        bot_dir_input = _prompt(
            "Path to bot directory (must contain launcher.py)",
            str(default_bot_dir) if default_bot_dir else None,
        )
        bot_dir = Path(bot_dir_input).expanduser().resolve()
        if (bot_dir / "launcher.py").is_file():
            break
        print("launcher.py not found in that directory. Try again.")

    host = _prompt("Heartbeat host", "127.0.0.1")
    port = int(_prompt("Heartbeat port", "5555"))
    timeout_seconds = int(_prompt("Timeout seconds before restart", "300"))
    startup_timeout_seconds = int(
        _prompt("Startup timeout seconds before restart", "600")
    )
    python_exe = _prompt("Python executable", "python3.11")
    process_name = _prompt("Process name to kill", "Fable")

    config = {
        "bot_dir": str(bot_dir),
        "host": host,
        "port": port,
        "timeout_seconds": timeout_seconds,
        "startup_timeout_seconds": startup_timeout_seconds,
        "python_exe": python_exe,
        "process_name": process_name,
    }

    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    logger.info("Wrote config to %s", config_path)
    return config


def _load_config(config_path: Path, logger: logging.Logger) -> dict[str, Any]:
    if not config_path.exists():
        return _create_config_interactive(config_path, logger)
    return json.loads(config_path.read_text(encoding="utf-8"))


def _kill_processes(process_name: str, logger: logging.Logger) -> int:
    killed = 0
    try:
        import psutil  # type: ignore
    except Exception:
        psutil = None

    if psutil is not None:
        current_pid = os.getpid()
        terminated = []
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if proc.info["pid"] == current_pid:
                    continue
                name = proc.info.get("name") or ""
                cmdline = " ".join(proc.info.get("cmdline") or [])
                if name == process_name or process_name in cmdline:
                    proc.terminate()
                    killed += 1
                    terminated.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if terminated:
            _, alive = psutil.wait_procs(terminated, timeout=5)
            for proc in alive:
                try:
                    proc.kill()
                except Exception:
                    pass
        return killed

    # Fallback to pkill on Linux
    try:
        subprocess.run(
            ["pkill", "-x", process_name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return 1
    except FileNotFoundError:
        pass

    try:
        subprocess.run(
            ["pkill", "-f", process_name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return 1
    except FileNotFoundError:
        logger.error("pkill not available and psutil not installed; cannot kill.")
        return 0


def _restart_bot(bot_dir: Path, python_exe: str, logger: logging.Logger) -> None:
    if not (bot_dir / "launcher.py").is_file():
        logger.error("launcher.py not found in %s; cannot restart.", bot_dir)
        return
    try:
        subprocess.Popen(
            [python_exe, "launcher.py"],
            cwd=str(bot_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info("Restarted bot with %s launcher.py in %s", python_exe, bot_dir)
    except Exception as exc:
        logger.error("Failed to restart bot: %s", exc)


def _run_watchdog(config: dict[str, Any], logger: logging.Logger) -> None:
    host = str(config.get("host", "127.0.0.1"))
    port = int(config.get("port", 5555))
    timeout_seconds = int(config.get("timeout_seconds", 300))
    startup_timeout_seconds = int(config.get("startup_timeout_seconds", 600))
    python_exe = str(config.get("python_exe", "python3.11"))
    process_name = str(config.get("process_name", "Fable"))
    bot_dir = Path(str(config.get("bot_dir", "."))).expanduser().resolve()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    sock.settimeout(1.0)

    logger.info("Listening on %s:%s (UDP). Timeout=%ss", host, port, timeout_seconds)
    logger.info("Will kill process name '%s' and restart in %s", process_name, bot_dir)

    waiting_for_first = True
    last_seen: float | None = None
    last_restart = time.monotonic()

    while True:
        now = time.monotonic()
        try:
            data, addr = sock.recvfrom(2048)
            last_seen = time.monotonic()
            if waiting_for_first:
                waiting_for_first = False
                logger.info("Heartbeat initialized by %s: %s", addr, data.decode("utf-8", "ignore"))
        except socket.timeout:
            pass

        if waiting_for_first:
            if now - last_restart > startup_timeout_seconds:
                logger.warning(
                    "Startup heartbeat timeout exceeded (%ss). Restarting bot.",
                    startup_timeout_seconds,
                )
                killed = _kill_processes(process_name, logger)
                logger.info("Killed %s process(es) named %s", killed, process_name)
                _restart_bot(bot_dir, python_exe, logger)
                last_restart = time.monotonic()
        elif last_seen is not None and now - last_seen > timeout_seconds:
            logger.warning("Heartbeat timeout exceeded. Restarting bot.")
            killed = _kill_processes(process_name, logger)
            logger.info("Killed %s process(es) named %s", killed, process_name)
            _restart_bot(bot_dir, python_exe, logger)
            waiting_for_first = True
            last_restart = time.monotonic()


def main() -> int:
    parser = argparse.ArgumentParser(description="Heartbeat watchdog")
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_NAME,
        help="Path to config JSON file",
    )
    args = parser.parse_args()

    logger = _configure_logging()
    script_dir = Path(__file__).resolve().parent
    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute() and args.config == DEFAULT_CONFIG_NAME:
        config_path = script_dir / DEFAULT_CONFIG_NAME
    config_path = config_path.resolve()
    config = _load_config(config_path, logger)
    _run_watchdog(config, logger)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
