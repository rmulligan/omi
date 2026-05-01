from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid
import base64

import database.conversations as conversations_db
from models.conversation import Conversation, Structured, CreateConversationResponse
from models.conversation_enums import ConversationSource, CategoryEnum, ConversationStatus, ConversationVisibility
from models.conversation_photo import ConversationPhoto
from models.transcript_segment import TranscriptSegment
from utils.conversations.process_conversation import process_conversation
from utils.other import endpoints as auth

router = APIRouter()

class OmnimodalIngestionRequest(BaseModel):
    source: ConversationSource
    category: CategoryEnum = CategoryEnum.other
    text: str
    title: Optional[str] = None
    base64_photos: List[str] = []
    metadata: Dict[str, Any] = {}
    timestamp: Optional[datetime] = None

@router.post("/v1/lilly/ingest", tags=['lilly'])
async def ingest_omnimodal(request: OmnimodalIngestionRequest, uid: str = Depends(auth.get_current_user_uid)):
    # 1. Prepare conversation data
    created_at = request.timestamp if request.timestamp else datetime.now(timezone.utc)
    id = str(uuid.uuid4())
    
    # 2. Handle photos
    photos = []
    for b64 in request.base64_photos:
        photos.append(ConversationPhoto(
            id=str(uuid.uuid4()),
            base64=b64,
            created_at=created_at
        ))
        
    # 3. Create Structured data
    structured = Structured(
        title=request.title if request.title else f"{request.source.value.replace('_', ' ').capitalize()} Event",
        overview=request.text,
        category=request.category,
        emoji='',
    )
    
    # 4. Create Conversation
    conversation = Conversation(
        id=id,
        created_at=created_at,
        started_at=created_at,
        finished_at=created_at,
        source=request.source,
        structured=structured,
        transcript_segments=[],
        photos=photos,
        external_data=request.metadata,
        status=ConversationStatus.completed,
    )
    
    # 5. Save to database
    conversations_db.upsert_conversation(uid, conversation.dict())
    
    # 6. Trigger processing
    processed_conversation = process_conversation(uid, 'en', conversation, force_process=True)
    
    # 7. Post-processing Correction (Preserve user-provided Lilly data)
    if request.category:
        processed_conversation.structured.category = request.category
    if request.title:
        processed_conversation.structured.title = request.title
    
    # Force another upsert to ensure the category is persisted
    conversations_db.upsert_conversation(uid, processed_conversation.dict())
    
    return CreateConversationResponse(conversation=processed_conversation, messages=[])
