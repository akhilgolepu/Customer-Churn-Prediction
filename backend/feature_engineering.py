import pandas as pd

def engineer_features(raw):
    """
    raw: PredictionRequest (Pydantic model)
    return: pd.DataFrame with engineered features
    """


    # Derived features
    total_service = sum([
        raw.PhoneService == "Yes",
        raw.MultipleLines == "Yes",
        raw.OnlineSecurity == "Yes",
        raw.OnlineBackup == "Yes",
        raw.DeviceProtection == "Yes",
        raw.TechSupport == "Yes",
        raw.StreamingTV == "Yes",
        raw.StreamingMovies == "Yes"
    ])

    is_fiber_customer = 1 if raw.InternetService == "Fiber optic" else 0
    is_month_to_month = 1 if raw.Contract == "Month-to-month" else 0
    payment_risk = 1 if raw.PaymentMethod == "Electronic check" else 0

    has_phone_and_internet = int(
        raw.PhoneService == "Yes" and raw.InternetService != "No"
    )

    tech_issue_risk = int(
        raw.OnlineSecurity == "No"
        and raw.TechSupport == "No"
        and raw.InternetService == "No"
    )

    if raw.tenure <= 6:
        tenure_group = "0-6"
    elif raw.tenure <= 12:
        tenure_group = "6-12"
    elif raw.tenure <= 24:
        tenure_group = "12-24"
    elif raw.tenure <= 48:
        tenure_group = "24-48"
    else:
        tenure_group = "48+"

    # FINAL FEATURES THAT GOES INTO THE MODEL

    features = {
        "MonthlyCharges": raw.MonthlyCharges,
        "tenure": raw.tenure,
        "TotalCharges": raw.TotalCharges,
        "SeniorCitizen": raw.SeniorCitizen,
        "TotalServices": total_service,
        "IsFiberCustomer": is_fiber_customer,
        "IsMonthToMonth": is_month_to_month,
        "TechIssueRisk": tech_issue_risk,
        "PaymentRisk": payment_risk,
        "HasPhoneAndInternet": has_phone_and_internet,
        "Partner": raw.Partner,
        "Dependents": raw.Dependents,
        "PhoneService": raw.PhoneService,
        "MultipleLines": raw.MultipleLines,
        "InternetService": raw.InternetService,
        "OnlineSecurity": raw.OnlineSecurity,
        "OnlineBackup": raw.OnlineBackup,
        "DeviceProtection": raw.DeviceProtection,
        "TechSupport": raw.TechSupport,
        "StreamingTV": raw.StreamingTV,
        "StreamingMovies": raw.StreamingMovies,
        "Contract": raw.Contract,
        "PaperlessBilling": raw.PaperlessBilling,
        "PaymentMethod": raw.PaymentMethod,
        "TenureGroup": tenure_group,
    }

    return pd.DataFrame([features])