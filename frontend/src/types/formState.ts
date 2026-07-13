export interface FormState {
    MonthlyCharges: number;
    tenure: number;
    TotalCharges: number;
    SeniorCitizen: 0 | 1;

    Partner: "Yes" | "No";
    Dependents: "Yes" | "No";

    PhoneService: "Yes" | "No";
    MultipleLines: "Yes" | "No" | "No phone service";

    InternetService: "No" | "DSL" | "Fiber optic";
    OnlineSecurity: "Yes" | "No" | "No internet service";
    OnlineBackup: "Yes" | "No" | "No internet service";
    DeviceProtection: "Yes" | "No" | "No internet service";
    TechSupport: "Yes" | "No" | "No internet service";
    StreamingTV: "Yes" | "No" | "No internet service";
    StreamingMovies: "Yes" | "No" | "No internet service";

    Contract: "Month-to-month" | "One year" | "Two year";
    PaperlessBilling: "Yes" | "No";
    PaymentMethod:
        | "Electronic check"
        | "Mailed check"
        | "Bank transfer (automatic)"
        | "Credit card (automatic)";
}
