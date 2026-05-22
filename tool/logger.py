import logging


logger = logging.getLogger("tourism-base")
logger.setLevel(logging.INFO)

if not logger.handlers:
    try:
        import colorlog

        handler = colorlog.StreamHandler()
        handler.setFormatter(
            colorlog.ColoredFormatter(
                "%(log_color)s%(asctime)s - %(filename)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
                log_colors={
                    "DEBUG": "cyan",
                    "INFO": "green",
                    "WARNING": "yellow",
                    "ERROR": "red",
                    "CRITICAL": "bold_red",
                },
            )
        )
    except Exception:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s - %(filename)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
