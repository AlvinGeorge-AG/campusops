from enum import Enum
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

class EventStatus(str, Enum):
    DRAFT = "draft"
    ROOM_IDENTIFIED = "room_identified"
    PENDING_APPROVAL = "pending_approval"
    LIVE = "live"
    CLOSED = "closed"

class Event(BaseModel):
    id: str = ""
    org: str = ""
    title: str = ""
    date: str = ""  # YYYY-MM-DD
    expected_headcount: int = 0
    room: Optional[str] = None
    room_capacity: Optional[int] = None
    status: EventStatus = EventStatus.DRAFT
    form_id: Optional[str] = None
    form_link: Optional[str] = None
    sheet_link: Optional[str] = None
    sheet_id: Optional[str] = None
    form_fields_json: Optional[str] = None  # JSON array of chosen fields for deterministic form creation
    registrant_count: int = 0
    announcement_sent: bool = False
    reminder_sent: bool = False
    created_at: str = ""

    def ensure_id(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()
        return self
