"""Production editing API request contract."""
from typing import Dict, List, Optional
from pydantic import BaseModel


class EditScriptRequest(BaseModel):
    episode_id: str
    edit_type: str
    line_index: Optional[int] = None
    new_content: Optional[Dict] = None
    new_order: Optional[List[int]] = None
    tone_adjustment: Optional[str] = None
    expansion_words: Optional[int] = None
    section_start: Optional[int] = None
    section_end: Optional[int] = None
    instructions: str = ""


