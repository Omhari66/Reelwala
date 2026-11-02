import urllib.parse
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.messaging.twilio_security import verify_twilio_signature
from app.models.base import get_db, utcnow
from app.models.entities import Business, Conversation, Message

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/twilio")
async def twilio_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_twilio_signature: str | None = Header(None, alias="X-Twilio-Signature"),
) -> dict[str, Any]:
    """Inbound webhook for Twilio WhatsApp messages with signature validation and deduplication."""
    content_type = request.headers.get("content-type", "")
    body_bytes = await request.body()

    if "application/x-www-form-urlencoded" in content_type or not content_type:
        raw_text = body_bytes.decode("utf-8", errors="replace")
        parsed = urllib.parse.parse_qs(raw_text, keep_blank_values=True)
        params = {k: v[0] for k, v in parsed.items()}
    else:
        try:
            form_data = await request.form()
            params = {k: str(v) for k, v in form_data.items()}
        except Exception:
            raw_text = body_bytes.decode("utf-8", errors="replace")
            parsed = urllib.parse.parse_qs(raw_text, keep_blank_values=True)
            params = {k: v[0] for k, v in parsed.items()}


    # Validate Twilio signature
    alt_url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/webhooks/twilio" if settings.PUBLIC_BASE_URL else None
    is_valid = verify_twilio_signature(
        url=str(request.url),
        params=params,
        signature=x_twilio_signature,
        auth_token=settings.TWILIO_AUTH_TOKEN,
        alternate_url=alt_url,
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio signature",
        )

    # Provider message ID for deduplication
    message_sid = params.get("MessageSid")
    if not message_sid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing MessageSid parameter",
        )

    # Check deduplication
    existing_message = db.query(Message).filter(Message.provider_msg_id == message_sid).first()
    if existing_message:
        return {
            "status": "ignored",
            "reason": "duplicate",
            "message_sid": message_sid,
        }

    # Extract sender phone
    from_raw = params.get("From", "")
    phone_e164 = from_raw.replace("whatsapp:", "").strip()
    if not phone_e164:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing From phone number",
        )

    # Lookup or initialize Business
    business = db.query(Business).filter(Business.phone_e164 == phone_e164).first()
    if not business:
        profile_name = params.get("ProfileName") or "New Business"
        business = Business(
            phone_e164=phone_e164,
            name=profile_name,
            language="hinglish",
        )
        db.add(business)
        db.flush()

    # Lookup or initialize Conversation
    conversation = db.query(Conversation).filter(Conversation.business_id == business.id).first()
    if not conversation:
        conversation = Conversation(
            business_id=business.id,
            state="NEW_USER",
        )
        db.add(conversation)
        db.flush()

    # Determine message type and media attachments
    num_media = int(params.get("NumMedia", "0"))
    msg_type = "text"
    media_url = None
    if num_media > 0:
        media_url = params.get("MediaUrl0")
        content_type = params.get("MediaContentType0", "").lower()
        if "video" in content_type:
            msg_type = "video"
        elif "image" in content_type:
            msg_type = "image"
        elif "audio" in content_type:
            msg_type = "audio"
        else:
            msg_type = "media"

    msg = Message(
        conversation_id=conversation.id,
        direction="in",
        type=msg_type,
        body=params.get("Body"),
        media_id=media_url,
        provider_msg_id=message_sid,
    )
    db.add(msg)
    conversation.last_message_at = utcnow()
    db.commit()

    # Route text or audio messages to conversation handler
    reply_text = None
    if msg_type == "text":
        from app.conversation.handlers import handle_inbound_message
        from app.messaging import get_messaging_provider

        provider = get_messaging_provider()
        reply_text = handle_inbound_message(
            db=db,
            business=business,
            conversation=conversation,
            text=params.get("Body"),
            media_url=media_url,
            provider=provider,
        )
    elif msg_type == "audio":
        import uuid

        from app.conversation import copy
        from app.conversation.handlers import handle_inbound_message
        from app.conversation.transcribe import transcribe_voice_note
        from app.messaging import get_messaging_provider

        provider = get_messaging_provider()
        if not settings.ENABLE_VOICE_NOTES:
            reply_text = copy.VOICE_NOTE_DISABLED
            provider.send_text(business.phone_e164, reply_text)
        else:
            transcription = None
            if media_url:
                dest_audio = f"data/voice_notes/{uuid.uuid4().hex[:8]}.ogg"
                provider.download_media(media_url, dest_audio)
                transcription = transcribe_voice_note(dest_audio)

            if transcription:
                reply_text = handle_inbound_message(
                    db=db,
                    business=business,
                    conversation=conversation,
                    text=transcription,
                    media_url=None,
                    provider=provider,
                )
            else:
                reply_text = copy.VOICE_NOTE_DISABLED
                provider.send_text(business.phone_e164, reply_text)


    return {
        "status": "received",
        "message_sid": message_sid,
        "message_id": msg.id,
        "type": msg_type,
        "reply": reply_text,
    }

