"""Authorization dependencies for OCR tool module routes."""

from app.core.security.permission_codes import FEATURE_OCR
from app.core.security.permission_deps import make_require_feature_workspace

require_ocr_workspace = make_require_feature_workspace(FEATURE_OCR)
