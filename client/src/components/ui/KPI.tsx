import { useEffect, useState } from "react";

interface KPIProps {
    title: string;
    value: number | string;
    suffix?: string;
    delta?: number;
}

export default function KPI({ title, value, suffix = "", delta }: KPIProps) {
    const isNumeric = typeof value === "number";
    const [displayValue, setDisplayValue] = useState(isNumeric ? value : 0);

    useEffect(() => {
        if (!isNumeric) return;

        let current = 0;
        const duration = 260;
        const stepTime = 16;
        const steps = duration / stepTime;
        const increment = value / steps;

        const interval = setInterval(() => {
            current += increment;
            if (current >= value) {
                setDisplayValue(value);
                clearInterval(interval);
            } else {
                setDisplayValue(current);
            }
        }, stepTime);

        return () => clearInterval(interval);
    }, [value, isNumeric]);

    const isPercent = suffix.includes("%");
    const valueLabel = isNumeric
        ? isPercent
            ? displayValue.toFixed(1)
            : Math.round(displayValue).toString()
        : value;
    const deltaLabel = typeof delta === "number" ? `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}%` : null;
    const deltaClass = delta === undefined
        ? ""
        : delta < 0
        ? "text-success bg-success/10"
        : "text-copper bg-copper/10";

    return (
        <div className="rounded-2xl border border-border bg-surface p-4 shadow-[0_8px_22px_rgba(31,42,42,0.06)] transition hover:-translate-y-0.5">
            <p className="text-[11px] uppercase tracking-[0.12em] text-muted">{title}</p>
            <div className="mt-2 flex items-end justify-between">
                <p className="text-3xl font-bold text-ink">{valueLabel}{suffix}</p>
                {deltaLabel && (
                    <span className={`rounded-full px-2 py-1 text-xs font-semibold ${deltaClass}`}>
                        {deltaLabel}
                    </span>
                )}
            </div>
        </div>
    );
}