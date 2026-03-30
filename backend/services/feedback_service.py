from repositories.feedback_repository import FeedbackRepository


class FeedbackService:
    def __init__(self, repo: FeedbackRepository) -> None:
        self._repo = repo

    def add_feedback(self, prediction_id: str, useful: bool, comment: str | None):
        return self._repo.add_feedback(prediction_id=prediction_id, useful=useful, comment=comment)

    def add_outcome(self, prediction_id: str, actual_churn: bool, notes: str | None):
        return self._repo.add_outcome(prediction_id=prediction_id, actual_churn=actual_churn, notes=notes)

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
