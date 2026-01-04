export default function Charts() {
  return (
    <div className="mt-4 p-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 rounded-md">
        <div className="rounded-xl border border-sand p-4">
          <p className="text-sm text-steel">Top Drivers (demo)</p>
          <ul className="mt-2 space-y-1 text-sm text-ink">
            <li>Contract: Month-to-month</li>
            <li>InternetService: Fiber optic</li>
            <li>PaymentMethod: Electronic check</li>
          </ul>
        </div>

        <div className="rounded-xl border border-sand p-4">
          <p className="text-sm text-steel">Charges Distribution (demo)</p>
          <div className="mt-2 h-24 bg-gradient-to-r from-sand to-taupe rounded" />
        </div>

        <div className="rounded-xl border border-sand p-4">
          <p className="text-sm text-steel">Tenure Breakdown (demo)</p>
          <div className="mt-2 grid grid-cols-5 gap-2">
            {["0-6","6-12","12-24","24-48","48+"].map((label, i) => (
              <div key={label} className="text-center rounded-md">
                <div className="mx-auto w-6 rounded bg-steel" style={{ height: `${20 + i * 8}px` }} />
                <span className="mt-1 block text-xs text-taupe">{label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
