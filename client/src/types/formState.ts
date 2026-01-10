export interface FormState {
    MonthlyCharges: number;
    tenure: number;
    TotalCharges: number;
    SeniorCitizen: number;

    Partner: string;
    Dependents: string;

    PhoneService: string;
    MultipleLines: string;

    InternetService: string;
    OnlineSecurity: string;
    OnlineBackup: string;
    DeviceProtection: string;
    TechSupport: string;

    StreamingTV: string;
    StreamingMovies: string;

    Contract: string;
    PaperlessBilling: string;
    PaymentMethod: string;
}