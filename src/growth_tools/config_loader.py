"""
YAML-based configuration loader for growth-tools.

Load order:
  1. Path in GROWTH_CONFIG env var (if set)
  2. growth.yml in current working directory
  3. Fall back to env vars for each setting

Example growth.yml:

    subreddits: [webdev, SaaS, startups]
    keywords: [migrate, moving from, switching to]
    scoring:
      hot_threshold: 80
      nurture_threshold: 50
    competitor_sdks: [firebase, appwrite, amplify]
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Optional dependency — stdlib yaml not available, so we try PyYAML
try:
    import yaml  # type: ignore[import-untyped]
    _YAML_AVAILABLE = True
except ImportError:
    yaml = None  # type: ignore[assignment]
    _YAML_AVAILABLE = False


# ─── defaults ────────────────────────────────────────────────────────────────
_DEFAULT_SUBREDDITS: List[str] = [
    "replit", "lovable", "vibecoding", "nocode",
    "sideproject", "saas", "entrepreneur",
]

_DEFAULT_KEYWORDS: List[str] = [
    "deploy", "deployment", "production", "aws", "migrate",
    "move off", "custom domain", "auth", "database",
    "github", "hosting", "scale",
]

_DEFAULT_SCORING: Dict[str, int] = {
    "hot_threshold": 80,
    "nurture_threshold": 50,
}

_DEFAULT_COMPETITOR_SDKS: List[str] = [
    "firebase", "appwrite", "amplify", "supabase-js",
    "convex", "pocketbase", "nhost",
]


# ─── internal helpers ────────────────────────────────────────────────────────

def _resolve_config_path() -> Optional[Path]:
    """Return the path to the YAML config file, or None if not found."""
    # 1. Explicit env var
    env_path = os.environ.get("GROWTH_CONFIG")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p
        logger.warning("GROWTH_CONFIG=%s does not exist; ignoring", env_path)

    # 2. growth.yml in CWD
    cwd_path = Path.cwd() / "growth.yml"
    if cwd_path.is_file():
        return cwd_path

    return None


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Parse a YAML file; returns empty dict on failure."""
    if not _YAML_AVAILABLE:
        logger.warning("PyYAML not installed; cannot load %s", path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            logger.warning("YAML root is not a mapping in %s; ignoring", path)
            return {}
        logger.info("Loaded growth config from %s", path)
        return data
    except Exception as exc:
        logger.warning("Failed to parse %s: %s", path, exc)
        return {}


def _env_list(key: str) -> Optional[List[str]]:
    """Read a comma-separated env var as a list, or None if unset."""
    raw = os.environ.get(key)
    if not raw:
        return None
    return [s.strip() for s in raw.split(",") if s.strip()]


# ─── public config class ─────────────────────────────────────────────────────

class GrowthConfig:
    """
    Merged configuration from YAML file + env vars + built-in defaults.

    Attributes
    ----------
    subreddits : list[str]
    keywords : list[str]
    hot_threshold : int
    nurture_threshold : int
    competitor_sdks : list[str]
    raw : dict
        The full parsed YAML dict (empty if no file was loaded).
    """

    def __init__(self, yaml_data: Optional[Dict[str, Any]] = None) -> None:
        self.raw: Dict[str, Any] = yaml_data or {}

        # --- subreddits ---
        self.subreddits: List[str] = (
            self.raw.get("subreddits")
            or _env_list("GROWTH_SUBREDDITS")
            or _DEFAULT_SUBREDDITS
        )

        # --- keywords ---
        self.keywords: List[str] = (
            self.raw.get("keywords")
            or _env_list("GROWTH_KEYWORDS")
            or _DEFAULT_KEYWORDS
        )

        # --- scoring thresholds ---
        scoring: Dict[str, Any] = self.raw.get("scoring") or {}
        self.hot_threshold: int = int(
            scoring.get("hot_threshold")
            or os.environ.get("GROWTH_HOT_THRESHOLD")
            or _DEFAULT_SCORING["hot_threshold"]
        )
        self.nurture_threshold: int = int(
            scoring.get("nurture_threshold")
            or os.environ.get("GROWTH_NURTURE_THRESHOLD")
            or _DEFAULT_SCORING["nurture_threshold"]
        )

        # --- competitor SDKs (for GitHub lead capture) ---
        self.competitor_sdks: List[str] = (
            self.raw.get("competitor_sdks")
            or _env_list("GROWTH_COMPETITOR_SDKS")
            or _DEFAULT_COMPETITOR_SDKS
        )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"GrowthConfig(subreddits={len(self.subreddits)}, "
            f"keywords={len(self.keywords)}, "
            f"hot={self.hot_threshold}, nurture={self.nurture_threshold}, "
            f"competitor_sdks={len(self.competitor_sdks)})"
        )


# ─── singleton loader ────────────────────────────────────────────────────────

_cached_config: Optional[GrowthConfig] = None


def load_config(force_reload: bool = False) -> GrowthConfig:
    """
    Load and return the merged GrowthConfig singleton.

    First load reads YAML (if present) and env vars; subsequent calls return
    the cached instance unless *force_reload* is True.
    """
    global _cached_config
    if _cached_config is not None and not force_reload:
        return _cached_config

    path = _resolve_config_path()
    yaml_data = _load_yaml(path) if path else {}
    _cached_config = GrowthConfig(yaml_data)
    logger.info("Growth config loaded: %s", _cached_config)
    return _cached_config
