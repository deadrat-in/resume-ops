from __future__ import annotations

import logging
import os
from typing import Any

from resume_ops_api.core.config import Settings

logger = logging.getLogger(__name__)


def setup_tracing(settings: Settings) -> None:
    """Configures global tracing integrations (Opik / LiteLLM) if ENABLE_TRACING is True."""
    if not settings.enable_tracing:
        logger.debug("Tracing is disabled (ENABLE_TRACING=false).")
        return

    try:
        import litellm

        if settings.opik_api_key:
            os.environ["OPIK_API_KEY"] = settings.opik_api_key
        if settings.opik_project_name:
            os.environ["OPIK_PROJECT_NAME"] = settings.opik_project_name
        if settings.opik_workspace:
            os.environ["OPIK_WORKSPACE"] = settings.opik_workspace

        callbacks: list[Any] = getattr(litellm, "success_callback", [])
        if "opik" not in callbacks:
            callbacks.append("opik")
            litellm.success_callback = callbacks
            logger.info(f"Opik tracing enabled for project '{settings.opik_project_name}'.")

    except ImportError:
        logger.warning("Opik tracing requested but 'opik' package is not installed.")
    except Exception as exc:
        logger.warning(f"Failed to initialize tracing: {exc}")
