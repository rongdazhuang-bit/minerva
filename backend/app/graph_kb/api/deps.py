"""Authorization dependencies for GraphKB module routes."""

from app.core.security.permission_codes import FEATURE_GRAPH_KB
from app.core.security.permission_deps import make_require_feature_workspace

# Ensures caller is a workspace member with feature:graph_kb entitlement.
require_graph_kb_workspace = make_require_feature_workspace(FEATURE_GRAPH_KB)
