from dataclasses import dataclass

from schemas.prediction import PredictionRequest
from services.prediction_service import PredictionService


@dataclass(frozen=True)
class ActionTemplate:
    key: str
    label: str
    rationale: str
    estimated_cost: float
    trigger_features: tuple[str, ...]
    base_impact: float


class RecommendationService:
    def __init__(self, prediction_service: PredictionService) -> None:
        self._prediction_service = prediction_service
        self._templates = [
            ActionTemplate(
                key="contract_migration",
                label="Promote annual contract migration",
                rationale="Month-to-month and contract-related churn signals are elevated.",
                estimated_cost=60.0,
                trigger_features=("Contract", "IsMonthToMonth"),
                base_impact=14.0,
            ),
            ActionTemplate(
                key="support_bundle",
                label="Offer premium support bundle",
                rationale="Support-related drivers suggest technical friction.",
                estimated_cost=45.0,
                trigger_features=("TechSupport", "TechIssueRisk", "OnlineSecurity"),
                base_impact=12.0,
            ),
            ActionTemplate(
                key="billing_stabilization",
                label="Incentivize autopay and billing stabilization",
                rationale="Billing/payment channels indicate higher payment risk.",
                estimated_cost=30.0,
                trigger_features=("PaymentRisk", "PaymentMethod"),
                base_impact=8.0,
            ),
            ActionTemplate(
                key="price_relief",
                label="Targeted loyalty discount",
                rationale="Price pressure signals are likely increasing churn probability.",
                estimated_cost=70.0,
                trigger_features=("MonthlyCharges", "TotalCharges"),
                base_impact=10.0,
            ),
        ]

    @staticmethod
    def _risk_tier(probability: float) -> str:
        if probability < 0.33:
            return "low"
        if probability < 0.66:
            return "medium"
        return "high"

    async def recommend(self, customer: PredictionRequest, budget: float) -> dict:
        prediction = await self._prediction_service.predict(customer, threshold=0.5)
        explanation = await self._prediction_service.explain(customer)

        drivers = explanation.get("top_drivers", [])
        positive_impacts = {item["feature"]: max(0.0, float(item["impact"])) for item in drivers}

        actions: list[dict] = []
        for template in self._templates:
            signal = sum(positive_impacts.get(feature, 0.0) for feature in template.trigger_features)
            signal_boost = min(1.8, 1.0 + signal)
            expected_impact_score = min(25.0, template.base_impact * signal_boost)
            confidence = min(0.95, 0.45 + (0.1 * len([f for f in template.trigger_features if f in positive_impacts])))
            impact_per_budget = expected_impact_score / template.estimated_cost
            actions.append(
                {
                    "key": template.key,
                    "label": template.label,
                    "rationale": template.rationale,
                    "expected_impact_score": round(expected_impact_score, 2),
                    "confidence": round(confidence, 3),
                    "estimated_cost": template.estimated_cost,
                    "impact_per_budget": round(impact_per_budget, 4),
                }
            )

        actions.sort(key=lambda item: item["impact_per_budget"], reverse=True)

        remaining = budget
        selected_actions: list[dict] = []
        for action in actions:
            if action["estimated_cost"] <= remaining:
                selected_actions.append(action)
                remaining -= action["estimated_cost"]

        total_selected_cost = sum(item["estimated_cost"] for item in selected_actions)
        total_expected_impact = sum(item["expected_impact_score"] for item in selected_actions)

        return {
            "prediction_id": prediction["predictionId"],
            "probability": prediction["probability"],
            "risk_tier": self._risk_tier(prediction["probability"]),
            "actions": actions,
            "selected_actions": selected_actions,
            "total_selected_cost": round(total_selected_cost, 2),
            "total_expected_impact": round(total_expected_impact, 2),
        }
