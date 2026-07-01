"""Authorization dependencies for S3 file module routes."""

from app.core.security.permission_codes import FEATURE_FILE_STORAGE
from app.core.security.permission_deps import make_require_feature_workspace

require_file_storage_workspace = make_require_feature_workspace(FEATURE_FILE_STORAGE)
