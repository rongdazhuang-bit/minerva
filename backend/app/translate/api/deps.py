"""Authorization dependencies for translate module routes."""

from app.core.security.permission_codes import FEATURE_TRANSLATE
from app.core.security.permission_deps import make_require_feature_workspace

require_translate_workspace = make_require_feature_workspace(FEATURE_TRANSLATE)
