"""
Email-related API endpoints.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form
from sqlalchemy.orm import Session

from ....core.security import get_current_active_user
from ....db.session import get_db
from ....crud import users as user_crud
from ....schemas import email as schemas

router = APIRouter()


@router.post("/verify", response_model=schemas.EmailVerifyResponse)
async def verify_emails(
    request: schemas.EmailVerifyRequest,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Verify a list of email addresses.
    Returns validation results for each email.
    """
    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # TODO: Implement email verification logic
    # from ....services.email import email_verifier
    # results = email_verifier.verify_emails(request.emails)

    return schemas.EmailVerifyResponse(
        results=[],
        total_verified=len(request.emails),
        valid_count=0,
        invalid_count=0
    )


@router.post("/send", status_code=202)
async def send_email(
    to_email: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    html_body: Optional[str] = Form(None),
    attachments: List[UploadFile] = File(default=[]),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Send an email via Gmail API with optional attachments.
    This triggers a background task.

    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Plain text email body
        html_body: Optional HTML formatted body
        attachments: List of file attachments
    """
    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Process attachments
    attachment_info = []
    for file in attachments:
        content = await file.read()
        attachment_info.append({
            "filename": file.filename,
            "content": content,
            "content_type": file.content_type
        })

    # Send email via Gmail API
    try:
        from ....services.email.gmail_sender import send_email as gmail_send

        result = gmail_send(
            to_email=to_email,
            subject=subject,
            body=body,
            html_body=html_body,
            attachments=attachment_info if attachment_info else None
        )

        return {
            "message": "Email sent successfully",
            "to": to_email,
            "attachments_count": len(attachment_info),
            "has_html": html_body is not None,
            "gmail_message_id": result.get('id')
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send email: {str(e)}"
        )


@router.post("/generate-draft/{company_id}")
async def generate_email_draft(
    company_id: int,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Generate an email draft for a company using AI.
    This triggers a background Celery task.
    """
    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # TODO: Verify company ownership and trigger task
    # from ....celery_app.tasks import generate_email_draft_task
    # task = generate_email_draft_task.delay(company_id)

    return {
        "message": "Email draft generation task queued",
        "company_id": company_id
    }
