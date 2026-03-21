import type { FormState } from "../types/formState";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

export async function predictChurn(formData: FormState) {
    const res = await fetch(`${BASE_URL}/predict`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(formData),
    });

    if (!res.ok) {
        const detail = await res.text().catch(() => "Unknown error");
        throw new Error(`Prediction failed (${res.status}): ${detail}`);
    }

    return await res.json();
}

export async function explainChurn(formData: FormState) {
    const res = await fetch(`${BASE_URL}/explain`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(formData),
    });

    if (!res.ok) {
        const detail = await res.text().catch(() => "Unknown error");
        throw new Error(`Explanation failed (${res.status}): ${detail}`);
    }

    return await res.json();
}