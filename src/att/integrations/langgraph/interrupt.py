"""TrustInterrupt — interrupt raised on quarantine/block actions."""

from __future__ import annotations

from typing import Any

try:
    from langgraph.errors import GraphInterrupt as _GraphInterrupt

    class TrustInterrupt(_GraphInterrupt):  # type: ignore[misc]
        """Raised when trust telemetry triggers quarantine or block.

        Inherits from ``langgraph.errors.GraphInterrupt`` so orchestrators
        can catch it as a normal graph interruption.

        Example::

            try:
                graph.invoke(state)
            except TrustInterrupt as e:
                print(e.evaluation["recommended_action"])  # "quarantine"
                print(e.evaluation["evidence"])
        """

        evaluation: dict[str, Any]

        def __init__(self, evaluation: dict[str, Any]) -> None:
            self.evaluation = evaluation
            action = evaluation.get("recommended_action", "unknown")
            risk_score = evaluation.get("risk_score", -1)
            severity = evaluation.get("severity", "unknown")
            super().__init__(
                f"Trust telemetry interrupted: {action} "
                f"(risk_score={risk_score}, severity={severity})"
            )

except ImportError:

    class TrustInterrupt(RuntimeError):  # type: ignore[no-redef]  # noqa: N818
        """Fallback when langgraph is not installed."""

        evaluation: dict[str, Any]

        def __init__(self, evaluation: dict[str, Any]) -> None:
            self.evaluation = evaluation
            action = evaluation.get("recommended_action", "unknown")
            risk_score = evaluation.get("risk_score", -1)
            severity = evaluation.get("severity", "unknown")
            super().__init__(
                f"Trust telemetry interrupted: {action} "
                f"(risk_score={risk_score}, severity={severity})"
            )
