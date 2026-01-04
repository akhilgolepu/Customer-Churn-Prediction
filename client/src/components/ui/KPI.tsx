interface KPIProps {
    title: string;
    value: string | number;
}


export default function KPI({ title, value }: KPIProps) {
    return (
        <div className="rounded-xl border border-sand bg-paper p-4">
            <p className="text-sm text-steel uppercase tracking-wide">{title}</p>
            <p className="mt-1 text-2xl font-bold text-ink">{value}</p>
        </div>
    );
}