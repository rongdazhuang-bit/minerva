"""Authorization dependencies for LLM module routes."""

from app.core.security.permission_codes import FEATURE_AGENT
from app.core.security.permission_deps import make_require_feature_workspace

require_agent_workspace = make_require_feature_workspace(FEATURE_AGENT)
