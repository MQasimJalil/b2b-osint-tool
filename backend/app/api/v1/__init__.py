"""API v1 router."""
from fastapi import APIRouter
from .endpoints import auth, companies, products, users, discovery, enrichment, email, rag, websocket, jobs, campaigns

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(companies.router, prefix="/companies", tags=["companies"])
api_router.include_router(products.router, prefix="/products", tags=["products"])
api_router.include_router(discovery.router, prefix="/discovery", tags=["discovery"])
api_router.include_router(enrichment.router, prefix="/enrichment", tags=["enrichment"])
api_router.include_router(email.router, prefix="/email", tags=["email"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(rag.router, prefix="/rag", tags=["rag"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(websocket.router, prefix="", tags=["websocket"])