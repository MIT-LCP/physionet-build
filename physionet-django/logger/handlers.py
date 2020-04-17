import datetime
import logging
import random
import json
import pdb

from django.utils import timezone
import logger


class DBHandler(logging.Handler, object):
    """
    This handler will add logs to a database model defined in settings.py
    
    The model has to be set on the emit function and set to None at init.
    """

    def __init__(self, model=None):
        super(DBHandler, self).__init__()
        self.model = model

    def emit(self, record):
        """
        Create the logger object
        """
        log_entry = logger.models.DBLogEntry(level=record.levelname,
                                             message=self.format(record),
                                             asctime=record.asctime,
                                             msg=record.msg,
                                             user=None,
                                             core_project=None,
                                             module='{0}.{1}'.format(
                                                 record.name, record.funcName))
        if hasattr(record, 'user'):
            log_entry.user = record.user

        if hasattr(record, 'core_project'):
            log_entry.core_project = record.core_project

        log_entry.save()
