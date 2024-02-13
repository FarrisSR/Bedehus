
import logging
from logging.handlers import SysLogHandler

LOG_FILE = "SyslogTest.log"
def setup_logging():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    # File handler
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(logging.INFO)
    file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(file_format)
    logger.addHandler(console_handler)

    # Syslog handler
    syslog_handler = SysLogHandler(address=('10.253.4.1', 5514))
    syslog_handler.setLevel(logging.INFO)
    syslog_format = logging.Formatter('%(asctime)s | %(levelname)s | %(name)s:%(funcName)s:%(lineno)d - %(message)s')
    syslog_handler.setFormatter(syslog_format)
    logger.addHandler(syslog_handler)

    return logger

def initialize():
    global logger
    logger = setup_logging()
    # Any other initialization code can go here

def main():
    try:
        initialize()
        logger.info("DEBUG learning to understand logging")
    except Exception as e:
        logger.error(f"Error in main: {e}")
        exit(1)


if __name__ == '__main__':
    main()

