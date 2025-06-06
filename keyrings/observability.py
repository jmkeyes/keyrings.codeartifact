import os
import logging

# create logger with 'spam_application'
logger = logging.getLogger("keyrings.codeartifact")

log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=log_level)
