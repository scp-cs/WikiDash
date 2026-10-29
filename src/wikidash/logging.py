import logging

LOGGER_FORMAT_STR = '[%(asctime)s][%(name)s][%(levelname)s]: %(message)s'

def create_logger(name: str | None) -> logging.Logger:
    """
    Create a logger with the specified name, `None` as name just sets formatting on the default logger
    """
    log = logging.getLogger(name)
    log.setLevel(logging.INFO)
    handler_st = logging.StreamHandler()
    handler_st.setFormatter(logging.Formatter(LOGGER_FORMAT_STR))
    log.addHandler(handler_st)
    return log