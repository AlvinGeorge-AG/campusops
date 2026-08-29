from enum import Enum
from pydantic import BaseModel, EmailStr, field_validator
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
    start_time: Optional[str] = None  # e.g. 3:30 PM
    end_time: Optional[str] = None  # e.g. 4:30 PM
    expected_headcount: int = 0
    room: Optional[str] = None
    room_capacity: Optional[int] = None
    speaker: Optional[str] = None  # e.g. Mr. Deepak Padmanabhan (Alumni)
    purpose: Optional[str] = None  # detailed purpose for letter
    chairperson: Optional[str] = None  # e.g. Arthana Sreekesh
    staff_in_charge: Optional[str] = None  # e.g. Aysha Fymin Majeed
    need_onfoot: bool = False  # whether on-foot publicity letter needed
    status: EventStatus = EventStatus.DRAFT
    form_id: Optional[str] = None
    form_link: Optional[str] = None
    sheet_link: Optional[str] = None
    sheet_id: Optional[str] = None
    form_fields_json: Optional[str] = None  # JSON array of chosen fields for deterministic form creation
    announcement_draft: Optional[str] = None  # preview announcement that authority reviews; reused after approval
    permission_letter: Optional[str] = None  # high-quality letter shown to club for edit/send
    onfoot_letter: Optional[str] = None  # on-foot publicity letter if needed
    email_draft: Optional[str] = None  # full email body shown to club (permission + attachments note)
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


class OrgSettings(BaseModel):
    org: str  # e.g. "FOSS MEC" - primary key
    institution_name: str = "Govt. Model Engineering College"
    institution_place: str = "Thrikkakara"
    faculty_email: str = "principal@example.com"  # principal / approval email
    announcement_recipients: str = "students@example.com"  # comma-separated
    chairperson: str = ""
    staff_in_charge: str = ""
    updated_at: str = ""

    @field_validator("org")
    @classmethod
    def org_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("org must not be empty")
        return v.strip()

    def ensure_updated(self):
        self.updated_at = datetime.utcnow().isoformat()
        return self
