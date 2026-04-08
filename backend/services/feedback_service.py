from repositories.feedback_repository import FeedbackRepository


class FeedbackService:
    def __init__(self, repo: FeedbackRepository, audit_service=None) -> None:
        self._repo = repo
        self._audit_service = audit_service

    def add_feedback(self, prediction_id: str, useful: bool, comment: str | None):
        result = self._repo.add_feedback(prediction_id=prediction_id, useful=useful, comment=comment)
        if self._audit_service is not None:
            self._audit_service.log(
                action="feedback_added",
                entity_type="prediction",
                entity_id=prediction_id,
                metadata={"useful": useful, "comment": comment},
            )
        return result

    def add_outcome(self, prediction_id: str, actual_churn: bool, notes: str | None):
        result = self._repo.add_outcome(prediction_id=prediction_id, actual_churn=actual_churn, notes=notes)
        if self._audit_service is not None:
            self._audit_service.log(
                action="outcome_added",
                entity_type="prediction",
                entity_id=prediction_id,
                metadata={"actual_churn": actual_churn, "notes": notes},
            )
        return result

    def summary(self) -> dict:
        feedback = self._repo.list_feedback()
        useful_count = sum(1 for item in feedback if item.useful)
        total = len(feedback)
        outcomes = self._repo.list_outcomes()
        return {
            "total_feedback": total,
            "useful_count": useful_count,
            "not_useful_count": total - useful_count,
            "useful_ratio": (useful_count / total) if total else 0.0,
            "outcomes_recorded": len(outcomes),
        }
