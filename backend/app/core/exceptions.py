"""
Custom Exception Classes for B2B OSINT Tool

Provides a consistent error handling framework with proper HTTP status codes
"""

from fastapi import HTTPException, status
from typing import Any, Dict, Optional


class B2BOSINTException(Exception):
    """Base exception for all B2B OSINT Tool errors"""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API response"""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "status_code": self.status_code,
            "details": self.details
        }


# Authentication & Authorization Errors
class AuthenticationError(B2BOSINTException):
    """Raised when authentication fails"""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, status.HTTP_401_UNAUTHORIZED)


class UnauthorizedError(B2BOSINTException):
    """Raised when user doesn't have permission"""

    def __init__(self, message: str = "Unauthorized access"):
        super().__init__(message, status.HTTP_403_FORBIDDEN)


class TokenExpiredError(AuthenticationError):
    """Raised when JWT token has expired"""

    def __init__(self, message: str = "Token has expired"):
        super().__init__(message)


class InvalidTokenError(AuthenticationError):
    """Raised when JWT token is invalid"""

    def __init__(self, message: str = "Invalid token"):
        super().__init__(message)


# Resource Errors
class ResourceNotFound(B2BOSINTException):
    """Raised when requested resource doesn't exist"""

    def __init__(self, resource: str, resource_id: str):
        message = f"{resource} with id '{resource_id}' not found"
        super().__init__(message, status.HTTP_404_NOT_FOUND)
        self.details = {"resource": resource, "id": resource_id}


class ResourceAlreadyExists(B2BOSINTException):
    """Raised when attempting to create a resource that already exists"""

    def __init__(self, resource: str, identifier: str):
        message = f"{resource} with identifier '{identifier}' already exists"
        super().__init__(message, status.HTTP_409_CONFLICT)
        self.details = {"resource": resource, "identifier": identifier}


class ResourceLocked(B2BOSINTException):
    """Raised when resource is locked by another user"""

    def __init__(self, resource: str, resource_id: str, locked_by: str):
        message = f"{resource} '{resource_id}' is currently locked by {locked_by}"
        super().__init__(message, status.HTTP_423_LOCKED)
        self.details = {
            "resource": resource,
            "id": resource_id,
            "locked_by": locked_by
        }


# Validation Errors
class ValidationError(B2BOSINTException):
    """Raised when input validation fails"""

    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message, status.HTTP_422_UNPROCESSABLE_ENTITY)
        if field:
            self.details = {"field": field}


class InvalidDomainError(ValidationError):
    """Raised when domain format is invalid"""

    def __init__(self, domain: str):
        super().__init__(f"Invalid domain format: {domain}", field="domain")


class InvalidEmailError(ValidationError):
    """Raised when email format is invalid"""

    def __init__(self, email: str):
        super().__init__(f"Invalid email format: {email}", field="email")


# Job Errors
class JobError(B2BOSINTException):
    """Base exception for job-related errors"""

    def __init__(self, job_id: str, message: str):
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.details = {"job_id": job_id}


class JobNotFound(ResourceNotFound):
    """Raised when job doesn't exist"""

    def __init__(self, job_id: str):
        super().__init__("Job", job_id)


class JobAlreadyRunning(B2BOSINTException):
    """Raised when attempting to start an already running job"""

    def __init__(self, job_id: str):
        message = f"Job '{job_id}' is already running"
        super().__init__(message, status.HTTP_409_CONFLICT)
        self.details = {"job_id": job_id}


class JobFailed(JobError):
    """Raised when job execution fails"""

    def __init__(self, job_id: str, reason: str):
        message = f"Job '{job_id}' failed: {reason}"
        super().__init__(job_id, message)
        self.details["reason"] = reason


class JobCancelled(JobError):
    """Raised when job is cancelled"""

    def __init__(self, job_id: str):
        message = f"Job '{job_id}' was cancelled"
        super().__init__(job_id, message)


# Discovery & Scraping Errors
class DiscoveryError(B2BOSINTException):
    """Base exception for discovery errors"""

    def __init__(self, message: str):
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR)


class ScrapingError(B2BOSINTException):
    """Raised when web scraping fails"""

    def __init__(self, url: str, reason: str):
        message = f"Failed to scrape {url}: {reason}"
        super().__init__(message, status.HTTP_502_BAD_GATEWAY)
        self.details = {"url": url, "reason": reason}


class ProxyError(B2BOSINTException):
    """Raised when proxy connection fails"""

    def __init__(self, proxy: str, reason: str):
        message = f"Proxy error ({proxy}): {reason}"
        super().__init__(message, status.HTTP_502_BAD_GATEWAY)
        self.details = {"proxy": proxy, "reason": reason}


class RateLimitError(B2BOSINTException):
    """Raised when rate limit is exceeded"""

    def __init__(self, service: str, retry_after: Optional[int] = None):
        message = f"Rate limit exceeded for {service}"
        super().__init__(message, status.HTTP_429_TOO_MANY_REQUESTS)
        self.details = {"service": service}
        if retry_after:
            self.details["retry_after"] = retry_after


# Email Errors
class EmailError(B2BOSINTException):
    """Base exception for email-related errors"""

    def __init__(self, message: str):
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR)


class EmailGenerationError(EmailError):
    """Raised when email generation fails"""

    def __init__(self, company_id: str, reason: str):
        message = f"Failed to generate email for company {company_id}: {reason}"
        super().__init__(message)
        self.details = {"company_id": company_id, "reason": reason}


class GmailAPIError(EmailError):
    """Raised when Gmail API call fails"""

    def __init__(self, operation: str, reason: str):
        message = f"Gmail API error during {operation}: {reason}"
        super().__init__(message)
        self.details = {"operation": operation, "reason": reason}


class EmailVerificationError(EmailError):
    """Raised when email verification fails"""

    def __init__(self, email: str, reason: str):
        message = f"Email verification failed for {email}: {reason}"
        super().__init__(message)
        self.details = {"email": email, "reason": reason}


# Database Errors
class DatabaseError(B2BOSINTException):
    """Base exception for database errors"""

    def __init__(self, message: str, operation: Optional[str] = None):
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR)
        if operation:
            self.details = {"operation": operation}


class ConnectionError(DatabaseError):
    """Raised when database connection fails"""

    def __init__(self, database: str):
        message = f"Failed to connect to {database} database"
        super().__init__(message, operation="connect")


class DuplicateKeyError(DatabaseError):
    """Raised when attempting to insert duplicate key"""

    def __init__(self, field: str, value: str):
        message = f"Duplicate value for {field}: {value}"
        super().__init__(message, operation="insert")
        self.details["field"] = field
        self.details["value"] = value


# External Service Errors
class ExternalServiceError(B2BOSINTException):
    """Raised when external service call fails"""

    def __init__(self, service: str, reason: str):
        message = f"External service error ({service}): {reason}"
        super().__init__(message, status.HTTP_502_BAD_GATEWAY)
        self.details = {"service": service, "reason": reason}


class APIKeyError(ExternalServiceError):
    """Raised when API key is invalid or missing"""

    def __init__(self, service: str):
        super().__init__(service, "Invalid or missing API key")


class QuotaExceededError(ExternalServiceError):
    """Raised when service quota is exceeded"""

    def __init__(self, service: str):
        super().__init__(service, "Quota exceeded")


# Configuration Errors
class ConfigurationError(B2BOSINTException):
    """Raised when configuration is invalid"""

    def __init__(self, setting: str, reason: str):
        message = f"Configuration error for '{setting}': {reason}"
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.details = {"setting": setting, "reason": reason}


# Helper function to convert exception to HTTP response
def exception_to_http_exception(exc: B2BOSINTException) -> HTTPException:
    """
    Convert B2BOSINTException to FastAPI HTTPException

    Args:
        exc: B2BOSINTException instance

    Returns:
        HTTPException ready to be raised
    """
    return HTTPException(
        status_code=exc.status_code,
        detail=exc.to_dict()
    )
