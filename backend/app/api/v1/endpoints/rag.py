"""
RAG (Retrieval-Augmented Generation) API endpoints.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ....core.security import get_current_active_user
from ....db.session import get_db
from ....crud import users as user_crud

router = APIRouter()


class RAGQueryRequest(BaseModel):
    """Request schema for RAG query."""
    query: str
    company_domain: Optional[str] = None
    top_k: int = 5
    # Context fields
    history: List[dict] = []  # List of {"role": "user"|"ai", "content": "..."} (Active Window)
    summary: Optional[str] = "" # Current conversation summary
    to_summarize: List[dict] = [] # Messages falling out of window to be added to summary


class RAGQueryResponse(BaseModel):
    """Response schema for RAG query."""
    query: str
    answer: str
    sources: List[dict]
    confidence: float
    # New context fields
    new_summary: Optional[str] = None
    suggested_questions: List[str] = []


@router.post("/query", response_model=RAGQueryResponse)
async def query_rag(
    request: RAGQueryRequest,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Query the B2B intelligence agent.
    Uses OpenAI Function Calling to retrieve data from:
    - Structured Company Profiles
    - Product Catalogs
    - Vector Knowledge Base (RAG)
    """
    from ....services.chat.agent import ChatAgent

    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        # Initialize Agent
        agent = ChatAgent()
        
        # Run Chat Loop
        result = await agent.run_chat(
            user_query=request.query,
            company_domain=request.company_domain,
            history=request.history,
            current_summary=request.summary,
            msgs_to_summarize=request.to_summarize
        )

        return RAGQueryResponse(
            query=request.query,
            answer=result["answer"],
            sources=result.get("sources", []),
            confidence=1.0 if result.get("sources") else 0.0,
            new_summary=result.get("new_summary"),
            suggested_questions=result.get("suggested_questions", [])
        )
    except Exception as e:
        print(f"Agent query error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to query agent: {str(e)}")


@router.post("/embed/{company_id}")
async def embed_company_data(
    company_id: int,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Embed company data into the RAG vector database.
    """
    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # TODO: Verify company ownership and embed data
    # from ....services.rag import rag
    # rag.embed_company(company_id)

    return {
        "message": "Company data embedding task queued",
        "company_id": company_id
    }
