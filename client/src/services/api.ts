export async function predictChurn(formData: any) {
    const res = await fetch("http://127.0.0.1:8000/predict", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(formData),
    });

    if (!res.ok) {
        throw new Error("Prediction failed");
    }

    return await res.json();
}

export async function explainChurn(formData: any) {
    const res = await fetch("http://127.0.0.1:8000/explain", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(formData),
    });

    if (!res.ok) {
        throw new Error("Explan failed");
    }

    return await res.json();
}