// frontend/src/components/StatsBar.jsx
/**
 * Four stat cards shown at the top of the dashboard.
 * Refreshes every time the parent re-fetches data.
 */
export default function StatsBar({ stats, transactions }) {
  const total = stats?.total_processed ?? transactions.length
  const flagged = stats?.total_flagged ?? transactions.filter(t => t.is_flagged).length
  const fraudRate = total > 0 ? ((flagged / total) * 100).toFixed(2) : '0.00'
  const critical = transactions.filter(t => t.risk_level === 'CRITICAL').length

  const cards = [
    {
      label: 'Total Processed',
      value: total.toLocaleString(),
      colour: 'text-blue-600',
      bg: 'bg-blue-50',
    },
    {
      label: 'Flagged',
      value: flagged.toLocaleString(),
      colour: 'text-orange-600',
      bg: 'bg-orange-50',
    },
    {
      label: 'Fraud Rate',
      value: `${fraudRate}%`,
      colour: fraudRate > 5 ? 'text-red-600' : 'text-green-600',
      bg: fraudRate > 5 ? 'bg-red-50' : 'bg-green-50',
    },
    {
      label: 'Critical',
      value: critical.toLocaleString(),
      colour: 'text-red-600',
      bg: 'bg-red-50',
    },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      {cards.map(card => (
        <div key={card.label}
          className={`${card.bg} rounded-lg p-4 border border-gray-100`}>
          <p className="text-sm text-gray-500">{card.label}</p>
          <p className={`text-2xl font-bold mt-1 ${card.colour}`}>
            {card.value}
          </p>
        </div>
      ))}
    </div>
  )
}