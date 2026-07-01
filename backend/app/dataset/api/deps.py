"""Authorization dependencies for dataset module routes."""

from app.core.security.permission_codes import FEATURE_DATASET
from app.core.security.permission_deps import make_require_feature_workspace

require_dataset_workspace = make_require_feature_workspace(FEATURE_DATASET)
