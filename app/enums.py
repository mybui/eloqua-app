from enum import Enum


class ServiceType(Enum):
    ACTION = "ACTION"
    CONTENT = "CONTENT"
    DECISION = "DECISION"
    FEEDER = "FEEDER"
    FIREHOSE = "FIREHOSE"
    MENU = "MENU"
