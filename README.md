# 🚀 Customer Churn Prediction with Explainable AI & What-if Simulation

Built a full-stack machine learning application that predicts customer churn, explains model decisions using SHAP, and enables real-time what-if simulations for business decision-making.

## 🔧 Tech Stack

- **Frontend**: React, TypeScript, TailwindCSS, Recharts
- **Backend**: FastAPI, Python
- **ML Model**: CatBoost Classifier
- **Explainability**: SHAP
- **Data**: Telecom churn dataset

## 🧠 Key Features

- **Predicts churn probability** with a production-ready ML pipeline
- **Backend-driven feature engineering** ensures training–inference parity
- **SHAP-based explanations** highlight top churn drivers per customer
- **What-if simulator** compares base vs simulated churn outcomes
- **Interactive dashboard** with trends, risk distribution, and KPIs

## 📊 Why CatBoost?

- **Native categorical feature handling**
- **Strong performance** on tabular business data
- **Stable probability outputs** suitable for decision support

## 🎯 Business Impact

- **Identifies high-risk customers early**
- **Explains why** a customer is likely to churn
- **Simulates retention strategies** before execution
- **Bridges the gap** between ML predictions and business actions

## 📌 What This Project Demonstrates

- **End-to-end ML system design**
- **Explainable AI (XAI)** in practice
- **Frontend–backend integration** for ML products
- **Production-grade feature engineering**
- **Model interpretability & scenario analysis**

## 🏁 Getting Started

### Prerequisites

- Node.js (v18+)
- Python (v3.9+)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Customer-Churn-Prediction
   ```

2. **Backend Setup**
   ```bash
   cd backend
   python -m venv venv
   # Windows
   .\venv\Scripts\activate
   # Mac/Linux
   source venv/bin/activate
   
   pip install -r requirements.txt
   ```

3. **Frontend Setup**
   ```bash
   cd ../client
   npm install
   ```

### 🚀 How to Run

1. **Start the Backend**
   ```bash
   cd backend
   uvicorn app:app --reload
   ```
   Server will run at `http://localhost:8000`

2. **Start the Frontend**
   ```bash
   cd client
   npm run dev
   ```
   App will run at `http://localhost:5173`

## 📸 Screenshots

![Dashboard Overview](client/src/assets/Screenshot%202026-01-18%20185507.png)
![Prediction Analysis](client/src/assets/Screenshot%202026-01-18%20185518.png)

