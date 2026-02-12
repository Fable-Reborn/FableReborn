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


def _normalized_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").lower()


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
    post_kill_wait_seconds = int(
        _prompt("Wait seconds after kill before forcing launcher restart", "10")
    )
    python_exe = _prompt("Python executable", "python3.11")
    process_name = _prompt("Process name to kill", "Fable")

    config = {
        "bot_dir": str(bot_dir),
        "host": host,
        "port": port,
        "timeout_seconds": timeout_seconds,
        "startup_timeout_seconds": startup_timeout_seconds,
        "post_kill_wait_seconds": post_kill_wait_seconds,
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


def _matches_named_process(proc: Any, process_name: str) -> bool:
    name = proc.info.get("name") or ""
    cmdline = " ".join(proc.info.get("cmdline") or [])
    return name == process_name or process_name in cmdline


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
                if _matches_named_process(proc, process_name):
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


def _count_processes(process_name: str) -> int | None:
    try:
        import psutil  # type: ignore
    except Exception:
        return None

    current_pid = os.getpid()
    count = 0
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["pid"] == current_pid:
                continue
            if _matches_named_process(proc, process_name):
                count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return count


def _is_launcher_process(proc: Any, bot_dir: Path) -> bool:
    cmdline_parts = [str(part) for part in (proc.info.get("cmdline") or [])]
    if not cmdline_parts:
        return False

    launcher_path = _normalized_path(bot_dir / "launcher.py")
    joined_cmdline = " ".join(cmdline_parts).replace("\\", "/").lower()
    if launcher_path in joined_cmdline:
        return True

    has_launcher_arg = any(
        Path(part).name.lower() == "launcher.py" for part in cmdline_parts
    )
    if not has_launcher_arg:
        return False

    try:
        proc_cwd = Path(proc.cwd()).resolve()
    except Exception:
        return False
    return _normalized_path(proc_cwd) == _normalized_path(bot_dir)


def _count_running_launchers(bot_dir: Path) -> int | None:
    try:
        import psutil  # type: ignore
    except Exception:
        return None

    current_pid = os.getpid()
    running = 0
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            if proc.info["pid"] == current_pid:
                continue
            if _is_launcher_process(proc, bot_dir):
                running += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return running


def _kill_launcher_processes(bot_dir: Path, logger: logging.Logger) -> int:
    try:
        import psutil  # type: ignore
    except Exception:
        logger.warning(
            "psutil is not available, cannot safely clean up launcher duplicates."
        )
        return 0

    current_pid = os.getpid()
    terminated = []
    killed = 0
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            if proc.info["pid"] == current_pid:
                continue
            if _is_launcher_process(proc, bot_dir):
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


def _recover_bot(
    bot_dir: Path,
    python_exe: str,
    process_name: str,
    logger: logging.Logger,
    wait_after_kill_seconds: int,
) -> None:
    killed_workers = _kill_processes(process_name, logger)
    logger.info("Killed %s process(es) named %s", killed_workers, process_name)

    running_launchers = _count_running_launchers(bot_dir)
    if running_launchers is None:
        _restart_bot(bot_dir, python_exe, logger)
        return

    if running_launchers > 1:
        logger.warning(
            "Detected %s launcher.py processes in %s. Restarting launcher cleanly.",
            running_launchers,
            bot_dir,
        )
        killed_launchers = _kill_launcher_processes(bot_dir, logger)
        logger.info("Killed %s launcher process(es)", killed_launchers)
        _restart_bot(bot_dir, python_exe, logger)
        return

    if running_launchers == 1 and killed_workers > 0:
        if wait_after_kill_seconds > 0:
            logger.info(
                "Waiting %ss for launcher recovery before forcing restart.",
                wait_after_kill_seconds,
            )
            time.sleep(wait_after_kill_seconds)
        running_workers = _count_processes(process_name)
        if running_workers is not None and running_workers > 0:
            logger.info(
                "Detected %s process(es) named %s after wait; skipping launcher spawn.",
                running_workers,
                process_name,
            )
            return
        logger.warning(
            "Launcher is running but no %s worker recovered after wait. Restarting launcher.",
            process_name,
        )
        killed_launchers = _kill_launcher_processes(bot_dir, logger)
        logger.info("Killed %s launcher process(es)", killed_launchers)
        _restart_bot(bot_dir, python_exe, logger)
        return

    if running_launchers == 1:
        logger.warning(
            "Launcher is running but no worker processes were killed. Restarting launcher."
        )
        killed_launchers = _kill_launcher_processes(bot_dir, logger)
        logger.info("Killed %s launcher process(es)", killed_launchers)
        _restart_bot(bot_dir, python_exe, logger)
        return

    _restart_bot(bot_dir, python_exe, logger)


def _run_watchdog(config: dict[str, Any], logger: logging.Logger) -> None:
    host = str(config.get("host", "127.0.0.1"))
    port = int(config.get("port", 5555))
    timeout_seconds = int(config.get("timeout_seconds", 300))
    startup_timeout_seconds = int(config.get("startup_timeout_seconds", 600))
    wait_after_kill_seconds = max(0, int(config.get("post_kill_wait_seconds", 10)))
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
                _recover_bot(
                    bot_dir,
                    python_exe,
                    process_name,
                    logger,
                    wait_after_kill_seconds,
                )
                last_restart = time.monotonic()
        elif last_seen is not None and now - last_seen > timeout_seconds:
            logger.warning("Heartbeat timeout exceeded. Restarting bot.")
            _recover_bot(
                bot_dir,
                python_exe,
                process_name,
                logger,
                wait_after_kill_seconds,
            )
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
