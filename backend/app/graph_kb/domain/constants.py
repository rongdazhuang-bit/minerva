"""GraphKB enums and Celery task names."""

ENGINE_GRAPHRAG = "graphrag"
ENGINE_LIGHTRAG = "lightrag"
ENGINES = frozenset({ENGINE_GRAPHRAG, ENGINE_LIGHTRAG})

PERMISSION_ONLY_ME = "only_me"
PERMISSION_PARTIAL_MEMBERS = "partial_members"
PERMISSION_ALL_TEAM_MEMBERS = "all_team_members"
PERMISSIONS = frozenset(
    {PERMISSION_ONLY_ME, PERMISSION_PARTIAL_MEMBERS, PERMISSION_ALL_TEAM_MEMBERS}
)

QUERY_LOCAL = "local"
QUERY_GLOBAL = "global"
QUERY_HYBRID = "hybrid"
QUERY_NAIVE = "naive"
QUERY_BASIC = "basic"
QUERY_MODES = frozenset(
    {QUERY_LOCAL, QUERY_GLOBAL, QUERY_HYBRID, QUERY_NAIVE, QUERY_BASIC}
)

SOURCE_UPLOAD_FILE = "upload_file"
SOURCE_PLAIN_TEXT = "plain_text"

STATUS_EMPTY = "empty"
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

JOB_INDEX = "index"
JOB_REINDEX = "reindex"
JOB_CLEANUP = "cleanup"

GRAPH_KB_INDEX_TASK_NAME = "graph_kb.index"
GRAPH_KB_CLEANUP_TASK_NAME = "graph_kb.cleanup"

ALLOWED_UPLOAD_SUFFIXES = frozenset({".txt", ".md", ".pdf", ".docx", ".html", ".csv"})
