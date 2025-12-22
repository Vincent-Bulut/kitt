from pydantic import BaseModel, model_validator
from enum import Enum, IntEnum
from datetime import date

class PriorityEnum(IntEnum):
    LOW = 3
    MEDIUM = 2
    HIGH = 1

class Portfolio(BaseModel):
    name: str
    start_date: date
    end_date: date | None = None
    description: str | None = None
    manager_name: str | None = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date doit être postérieure à start_date")
        return self
