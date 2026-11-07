"""Build the command that parks or starts the Fable dev bot.

The only legal replica counts are 0 and 1. The live deployment, fable-bot,
is not a target this module can name.
"""

from __future__ import annotations

# NUT and Lunar. Nobody else can start or stop the dev bot.
DEV_BOT_OPERATORS = frozenset({
    273652235588599808,
    295173706496475136,
})

NAMESPACE = "fable"
DEPLOYMENT = "fable-bot-dev"


def scale_argv(replicas: int) -> list[str]:
    """argv for `sudo k3s kubectl scale` of fable-bot-dev. replicas is 0 or 1."""
    if type(replicas) is not int or replicas not in (0, 1):
        raise ValueError("Replicas must be 0 or 1.")
    if DEPLOYMENT != "fable-bot-dev" or NAMESPACE != "fable":
        raise ValueError("Refusing to scale any deployment except fable-bot-dev.")
    return [
        "sudo",
        "-n",
        "k3s",
        "kubectl",
        "-n",
        "fable",
        "scale",
        "deploy/fable-bot-dev",
        f"--replicas={replicas}",
    ]
