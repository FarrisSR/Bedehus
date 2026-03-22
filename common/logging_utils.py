import logging
import logging.config
import socket
from pathlib import Path
from typing import Any, Dict


class HostnameFilter(logging.Filter):
    hostname = socket.gethostname()

    def filter(self, record: logging.LogRecord) -> bool:
        record.hostname = self.hostname
        return True


def resolve_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return base_dir / path


def setup_logging(
    logger_name: str,
    base_dir: Path,
    cfg: Dict[str, Any],
    *,
    default_config_file: str = "logging.config",
) -> logging.Logger:
    logger = logging.getLogger(logger_name)
    log_cfg = cfg.get("logging", {}).get("python_config_file", default_config_file)
    log_path = resolve_path(base_dir, log_cfg)
    try:
        logging.config.fileConfig(fname=str(log_path), disable_existing_loggers=False)
    except Exception:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
        )
    logger.setLevel(logging.INFO)
    logger.addFilter(HostnameFilter())
    return logger
