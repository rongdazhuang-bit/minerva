from arq.connections import RedisSettings

from app.config import settings
from app.worker import tasks


class WorkerSettings:
    functions = [tasks.handle_execution_tick]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    job_timeout = 300
    max_tries = 2
