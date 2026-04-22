from pydantic import BaseModel, Field
from typing import List, Dict, Optional


class UnavailableBlock(BaseModel):
    day: str          # "Mon" .. "Sun"
    start: str        # "HH:MM" 24h
    end: str


class StaffMember(BaseModel):
    id: str
    name: str
    role: str         # "Manager" | "Receptionist" | "Housekeeper" | "F&B" ...
    max_hours: int = Field(gt=0, le=80)
    unavailable: Optional[List[UnavailableBlock]] = []


class Shift(BaseModel):
    id: str
    day: str
    start: str
    end: str
    required_roles: Dict[str, int]   # e.g. {"Manager": 1, "Receptionist": 2}


class RosterRequest(BaseModel):
    staff: List[StaffMember]
    shifts: List[Shift]