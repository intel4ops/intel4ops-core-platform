from sqlalchemy.orm import Session

from app.models.gateway import ApiRequestAuditEvent
from app.schemas.api_common import RequestContext


class ApiGatewayService:
    def audit(
        self,
        db: Session,
        context: RequestContext,
        operation: str,
        outcome: str = "completed",
        status_code: int = 200,
    ) -> None:
        db.add(
            ApiRequestAuditEvent(
                organization_id=context.organization_id,
                request_id=context.request_id,
                correlation_id=context.correlation_id,
                client_code=context.client_code,
                actor_user_id=context.user_id,
                operation=operation,
                outcome=outcome,
                status_code=status_code,
                details={"actor_type": context.actor_type, "roles": context.roles},
            )
        )
        db.commit()


api_gateway_service = ApiGatewayService()
