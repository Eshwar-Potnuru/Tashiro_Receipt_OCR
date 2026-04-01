"""Phase 12A-2: Centralized Access Control Service

This service consolidates access-control logic that was previously scattered
across multiple modules (drafts.py, hq_view.py, hq_transfer.py, excel_source.py).

Design Principles:
    - Behavior-preserving: All decisions match existing inline logic exactly
    - Structured output: Returns AccessControlDecision for auditable decisions
    - Backward compatible: Existing inline helpers delegate to this service
    - Testable: All decision logic is unit-testable

Role Hierarchy:
    - WORKER: Can only access own drafts/receipts
    - ADMIN: Can access office-level data, elevated privileges
    - HQ: Can access all data, highest privileges

Current Phase Scope:
    - Centralizes role-checking logic
    - Provides decision-returning methods
    - Does NOT change who can access what from user perspective

Author: Phase 12A-2 - Access Control Core Centralization
Date: 2026-03-24
"""

from __future__ import annotations

from typing import Optional, Protocol, Union
from uuid import UUID

from app.models.phase12_contracts import (
    AccessControlDecision,
    AccessDecision,
    IAccessControlService,
)


class UserLike(Protocol):
    """Protocol for user-like objects that have user_id and role attributes."""
    user_id: Union[str, UUID]
    role: str


class DraftLike(Protocol):
    """Protocol for draft-like objects that have creator_user_id attribute."""
    creator_user_id: Optional[Union[str, UUID]]


class AccessControlService(IAccessControlService):
    """Centralized access control service.
    
    This service provides:
    1. Role classification methods (is_worker, is_admin, is_hq, is_admin_or_hq)
    2. Draft ownership checking
    3. Structured AccessControlDecision responses
    
    All logic matches the existing inline behavior exactly to ensure
    production behavior remains unchanged.
    
    Example:
        >>> service = AccessControlService()
        >>> # Simple role checks
        >>> service.is_worker(user)
        True
        >>> # Structured decision
        >>> decision = service.check_draft_access(user, draft, "edit")
        >>> if decision.is_allowed:
        ...     proceed_with_edit()
    """
    
    # =========================================================================
    # ROLE CLASSIFICATION (matches existing inline logic exactly)
    # =========================================================================
    
    @staticmethod
    def get_role_normalized(user: UserLike) -> str:
        """Get normalized uppercase role string from user object.
        
        Handles various role representations (string, enum, etc.) safely.
        
        Args:
            user: User-like object with role attribute
            
        Returns:
            Uppercase role string (e.g., "WORKER", "ADMIN", "HQ")
        """
        role = getattr(user, "role", "")
        # Handle enum-like objects
        if hasattr(role, "value"):
            role = role.value
        return str(role).upper()
    
    @staticmethod
    def is_worker(user: UserLike) -> bool:
        """Check if user has WORKER role.
        
        Matches existing _is_worker() logic in drafts.py exactly.
        
        Args:
            user: User-like object with role attribute
            
        Returns:
            True if role is WORKER
        """
        return AccessControlService.get_role_normalized(user) == "WORKER"
    
    @staticmethod
    def is_admin(user: UserLike) -> bool:
        """Check if user has ADMIN role.
        
        Args:
            user: User-like object with role attribute
            
        Returns:
            True if role is ADMIN
        """
        return AccessControlService.get_role_normalized(user) == "ADMIN"
    
    @staticmethod
    def is_hq(user: UserLike) -> bool:
        """Check if user has HQ role.
        
        Args:
            user: User-like object with role attribute
            
        Returns:
            True if role is HQ
        """
        return AccessControlService.get_role_normalized(user) == "HQ"
    
    @staticmethod
    def is_admin_or_hq(user: UserLike) -> bool:
        """Check if user has ADMIN or HQ role.
        
        Matches existing _is_admin_or_hq() logic in drafts.py exactly.
        Also matches _ensure_hq_or_admin() logic in hq_view.py, excel_source.py.
        
        Args:
            user: User-like object with role attribute
            
        Returns:
            True if role is ADMIN or HQ
        """
        return AccessControlService.get_role_normalized(user) in {"ADMIN", "HQ"}
    
    # =========================================================================
    # OWNERSHIP CHECKS (matches existing inline logic exactly)
    # =========================================================================
    
    @staticmethod
    def owns_draft(user: UserLike, draft: DraftLike) -> bool:
        """Check if user owns the draft (is the creator).
        
        Matches existing ownership logic in _assert_draft_access() exactly.
        
        Args:
            user: User-like object with user_id attribute
            draft: Draft-like object with creator_user_id attribute
            
        Returns:
            True if user created the draft
        """
        owner_user_id = str(draft.creator_user_id) if draft.creator_user_id else None
        current_user_id = str(user.user_id)
        return owner_user_id == current_user_id
    
    # =========================================================================
    # COMBINED ACCESS DECISIONS
    # =========================================================================
    
    @staticmethod
    def can_access_draft(user: UserLike, draft: DraftLike) -> bool:
        """Determine if user can access the draft.
        
        Current rules (matching existing behavior):
        - ADMIN and HQ can access any draft
        - WORKER can only access own drafts
        
        Args:
            user: User-like object
            draft: Draft-like object
            
        Returns:
            True if user can access the draft
        """
        # Non-workers (ADMIN, HQ) can access any draft
        if not AccessControlService.is_worker(user):
            return True
        # Workers can only access their own drafts
        return AccessControlService.owns_draft(user, draft)
    
    # =========================================================================
    # STRUCTURED DECISION METHODS (IAccessControlService implementation)
    # =========================================================================
    
    def check_access(
        self,
        actor_id: str,
        resource_type: str,
        resource_id: str,
        operation: str,
    ) -> AccessControlDecision:
        """Check if an operation is permitted.
        
        This is the generic interface method. For draft-specific checks,
        use check_draft_access() which accepts typed objects.
        
        This placeholder returns ALLOW by default for Phase 12A-2.
        More sophisticated logic will be added in later phases.
        
        Args:
            actor_id: User ID making the request
            resource_type: Type of resource (e.g., "draft", "excel_file")
            resource_id: ID of the specific resource
            operation: Operation being attempted
            
        Returns:
            AccessControlDecision with decision outcome
        """
        # Phase 12A-2: Basic implementation - defer to specific check methods
        # This generic method is a placeholder for future extension
        return AccessControlDecision(
            decision=AccessDecision.DEFER,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            operation=operation,
            reason="Generic check - use specific methods like check_draft_access()",
        )
    
    @staticmethod
    def check_draft_access(
        user: UserLike,
        draft: DraftLike,
        operation: str,
        draft_id: Optional[str] = None,
    ) -> AccessControlDecision:
        """Check if user can perform operation on draft.
        
        Returns structured AccessControlDecision for auditable access checks.
        
        Rules match existing inline behavior exactly:
        - ADMIN and HQ: ALLOW for all operations on any draft
        - WORKER: ALLOW only for own drafts, DENY otherwise
        
        Args:
            user: User-like object
            draft: Draft-like object
            operation: Operation being attempted (edit, delete, view, send)
            draft_id: Optional draft ID for decision record
            
        Returns:
            AccessControlDecision with decision and reason
        """
        actor_id = str(user.user_id)
        resource_id = draft_id or str(getattr(draft, "draft_id", "unknown"))
        
        # Non-workers (ADMIN, HQ) can access any draft
        if not AccessControlService.is_worker(user):
            role = AccessControlService.get_role_normalized(user)
            return AccessControlDecision(
                decision=AccessDecision.ALLOW,
                actor_id=actor_id,
                resource_type="draft",
                resource_id=resource_id,
                operation=operation,
                reason=f"{role} role has full draft access",
            )
        
        # Workers can only access their own drafts
        if AccessControlService.owns_draft(user, draft):
            return AccessControlDecision(
                decision=AccessDecision.ALLOW,
                actor_id=actor_id,
                resource_type="draft",
                resource_id=resource_id,
                operation=operation,
                reason="User owns this draft",
            )
        
        # Worker trying to access someone else's draft - DENY
        return AccessControlDecision(
            decision=AccessDecision.DENY,
            actor_id=actor_id,
            resource_type="draft",
            resource_id=resource_id,
            operation=operation,
            reason="WORKER can only access own drafts",
        )
    
    @staticmethod
    def check_admin_or_hq_required(
        user: UserLike,
        operation: str,
        resource_type: str = "endpoint",
        resource_id: str = "unknown",
    ) -> AccessControlDecision:
        """Check if user has ADMIN or HQ role for elevated operations.
        
        Matches logic in _ensure_hq_or_admin() across multiple modules.
        
        Args:
            user: User-like object
            operation: Operation being attempted
            resource_type: Type of resource (default: "endpoint")
            resource_id: ID of the specific resource
            
        Returns:
            AccessControlDecision allowing ADMIN/HQ, denying others
        """
        actor_id = str(user.user_id)
        
        if AccessControlService.is_admin_or_hq(user):
            role = AccessControlService.get_role_normalized(user)
            return AccessControlDecision(
                decision=AccessDecision.ALLOW,
                actor_id=actor_id,
                resource_type=resource_type,
                resource_id=resource_id,
                operation=operation,
                reason=f"{role} role has elevated access",
            )
        
        return AccessControlDecision(
            decision=AccessDecision.DENY,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            operation=operation,
            reason="ADMIN or HQ role required",
        )
    
    @staticmethod
    def check_admin_only(
        user: UserLike,
        operation: str,
        resource_type: str = "endpoint",
        resource_id: str = "unknown",
    ) -> AccessControlDecision:
        """Check if user has ADMIN role for admin-only operations.
        
        Matches logic in _ensure_admin_only() in hq_transfer.py.
        
        Args:
            user: User-like object
            operation: Operation being attempted
            resource_type: Type of resource (default: "endpoint")
            resource_id: ID of the specific resource
            
        Returns:
            AccessControlDecision allowing ADMIN only, denying others
        """
        actor_id = str(user.user_id)
        
        if AccessControlService.is_admin(user):
            return AccessControlDecision(
                decision=AccessDecision.ALLOW,
                actor_id=actor_id,
                resource_type=resource_type,
                resource_id=resource_id,
                operation=operation,
                reason="ADMIN role has full access",
            )
        
        return AccessControlDecision(
            decision=AccessDecision.DENY,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            operation=operation,
            reason="ADMIN role required",
        )


# Module-level singleton for convenient access
_access_control_service: Optional[AccessControlService] = None


def get_access_control_service() -> AccessControlService:
    """Get or create AccessControlService singleton.
    
    Returns:
        AccessControlService instance
    """
    global _access_control_service
    if _access_control_service is None:
        _access_control_service = AccessControlService()
    return _access_control_service


__all__ = [
    "AccessControlService",
    "get_access_control_service",
    "UserLike",
    "DraftLike",
]
