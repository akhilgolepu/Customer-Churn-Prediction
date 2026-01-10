import { useEffect, useState } from "react";

interface KPIProps {
    title: string;
    value: string | number;
}

export default function KPI({ title, value }: KPIProps) {
    const numericValue = typeof value === "number" ? value : Number(value);
    const [displayValue, setDisplayValue] = useState(0);

    useEffect(() => {
        if(isNaN(numericValue)) return;

        let start = 0;
        const duration = 600;
        const stepTime = 20;
        const steps = duration / stepTime;
        const increment = numericValue / steps;

        const interval = setInterval(() => {
            start += increment;
            if (start >= numericValue) {
                setDisplayValue(numericValue);
                clearInterval(interval);
            } else {
                setDisplayValue(Math.round(start));
            }
        }, stepTime);

        return () => clearInterval(interval);

    }, [numericValue]);

    return (
        <div className="rounded-xl border border-sand bg-paper p-4">
            <p className="text-sm text-steel uppercase tracking-wide">{title}</p>
            <p className="mt-1 text-2xl font-bold text-ink">{displayValue}</p>
        </div>
    );
}