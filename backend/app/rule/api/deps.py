"""Authorization dependencies for rule module routes."""

from app.core.security.permission_codes import FEATURE_RULES
from app.core.security.permission_deps import make_require_feature_workspace

require_rules_workspace = make_require_feature_workspace(FEATURE_RULES)
