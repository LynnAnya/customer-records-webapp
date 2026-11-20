import logging


class OneLine(logging.Filter):
    """Drop the traceback from a log record, keeping its one-line message.

    Used for requests with an unknown Host header: robots on the internet send
    them all day, and a full traceback for each would bury the useful logs.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.exc_info = None
        record.exc_text = None
        return True
