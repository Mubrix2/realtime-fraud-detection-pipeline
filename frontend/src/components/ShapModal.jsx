// frontend/src/components/ShapModal.jsx
import { useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  Cell, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import RiskBadge from './RiskBadge'
import ActionBadge from './ActionBadge'

/**
 * Full-screen modal showing SHAP explanation for a transaction.
 * Opens when a row is clicked. Closes on backdrop click or X button.
 */
export default function ShapModal({ transaction, onClose }) {
  if (!transaction) return null

  // Close on Escape key
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const reasons = transaction.top_reasons ?? []
  const isAutoApproved =
    transaction.note?.includes('Auto-approved') ||
    (!transaction.explanation_available &&
      transaction.fraud_probability === 0.0)

  const chartData = reasons
    .map(r => ({
      name: r.description.length > 35
        ? r.description.slice(0, 35) + '…'
        : r.description,
      value: r.shap_value,
      direction: r.direction,
      impact: r.impact,
      feature_value: r.feature_value,
    }))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))

  const fraudPct = (transaction.fraud_probability * 100).toFixed(1)
  const probColour =
    transaction.fraud_probability > 0.8
      ? 'text-red-600'
      : transaction.fraud_probability > 0.6
      ? 'text-orange-500'
      : 'text-green-600'

  return (
    // Backdrop
    <div
      className="fixed inset-0 bg-black/50 backdrop-blur-sm
                 flex items-center justify-center z-50 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      {/* Modal */}
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-3xl
                      max-h-[90vh] overflow-y-auto">

        {/* Header */}
        <div className="flex justify-between items-start p-6
                        border-b border-gray-100 sticky top-0 bg-white z-10">
          <div>
            <h2 className="text-lg font-bold text-gray-900">
              Transaction Assessment
            </h2>
            <p className="text-xs text-gray-400 font-mono mt-0.5">
              {transaction.transaction_id}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700 text-2xl
                       leading-none w-8 h-8 flex items-center justify-center
                       rounded-lg hover:bg-gray-100 transition-colors"
          >
            ✕
          </button>
        </div>

        <div className="p-6">

          {/* Auto-approved banner */}
          {isAutoApproved && (
            <div className="mb-5 px-4 py-3 bg-blue-50 border border-blue-200
                            rounded-lg text-sm text-blue-700">
              <strong>Auto-approved</strong> — {transaction.transaction?.type}{' '}
              transactions are outside the model's scoring scope. The fraud model
              was trained exclusively on TRANSFER and CASH_OUT transactions.
            </div>
          )}

          {/* Summary grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-gray-50 rounded-lg p-4">
              <p className="text-xs text-gray-500 mb-1">Decision</p>
              <ActionBadge action={transaction.action} />
            </div>
            <div className="bg-gray-50 rounded-lg p-4">
              <p className="text-xs text-gray-500 mb-1">Risk Level</p>
              {isAutoApproved
                ? <span className="text-xs text-gray-400 italic">out of scope</span>
                : <RiskBadge level={transaction.risk_level} />
              }
            </div>
            <div className="bg-gray-50 rounded-lg p-4">
              <p className="text-xs text-gray-500">Fraud Probability</p>
              <p className={`text-2xl font-bold mt-1 ${probColour}`}>
                {isAutoApproved ? '—' : `${fraudPct}%`}
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-4">
              <p className="text-xs text-gray-500">Anomaly</p>
              <p className="text-base font-semibold mt-1">
                {transaction.anomaly_severity}
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-4">
              <p className="text-xs text-gray-500">Amount</p>
              <p className="text-base font-semibold mt-1">
                ₦{Number(transaction.transaction?.amount ?? 0).toLocaleString()}
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-4">
              <p className="text-xs text-gray-500">Type</p>
              <p className="text-base font-semibold mt-1">
                {transaction.transaction?.type ?? '—'}
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-4">
              <p className="text-xs text-gray-500">Processing Time</p>
              <p className="text-base font-semibold mt-1">
                {transaction.processing_time_ms?.toFixed(1) ?? '—'} ms
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-4">
              <p className="text-xs text-gray-500">Is Flagged</p>
              <p className={`text-base font-semibold mt-1 ${
                transaction.is_flagged ? 'text-red-600' : 'text-green-600'
              }`}>
                {transaction.is_flagged ? 'Yes' : 'No'}
              </p>
            </div>
          </div>

          {/* SHAP chart — only for scored transactions */}
          {!isAutoApproved && chartData.length > 0 && (
            <div className="mb-6">
              <div className="flex justify-between items-center mb-3">
                <h3 className="font-semibold text-gray-800">
                  SHAP Feature Contributions
                </h3>
                <p className="text-xs text-gray-400">
                  Features that influenced the fraud probability
                </p>
              </div>

              <div className="bg-gray-50 rounded-lg p-4">
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart
                    data={chartData}
                    layout="vertical"
                    margin={{ top: 8, right: 24, bottom: 8, left: 16 }}
                  >
                    <XAxis
                      type="number"
                      tick={{ fontSize: 11 }}
                      tickFormatter={v => v.toFixed(2)}
                      label={{
                        value: 'SHAP Value (impact on fraud probability)',
                        position: 'insideBottom',
                        offset: -4,
                        fontSize: 10,
                        fill: '#9ca3af',
                      }}
                    />
                    <YAxis
                      type="category"
                      dataKey="name"
                      tick={{ fontSize: 11 }}
                      width={200}
                    />
                    <ReferenceLine x={0} stroke="#d1d5db" strokeWidth={1} />
                    <Tooltip
                      content={({ active, payload }) => {
                        if (!active || !payload?.length) return null
                        const d = payload[0].payload
                        return (
                          <div className="bg-white border border-gray-200
                                          rounded-lg shadow-lg p-3 text-xs max-w-xs">
                            <p className="font-medium text-gray-800 mb-1">
                              {d.name}
                            </p>
                            <p className={
                              d.direction === 'increased_risk'
                                ? 'text-red-600'
                                : 'text-green-600'
                            }>
                              {d.direction === 'increased_risk'
                                ? '▲ Increased fraud risk'
                                : '▼ Decreased fraud risk'}
                            </p>
                            <p className="text-gray-600 mt-1">
                              SHAP value: {d.value.toFixed(4)}
                            </p>
                            <p className="text-gray-500">
                              Impact: {d.impact}
                            </p>
                          </div>
                        )
                      }}
                    />
                    <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                      {chartData.map((entry, idx) => (
                        <Cell
                          key={idx}
                          fill={
                            entry.direction === 'increased_risk'
                              ? '#ef4444'
                              : '#22c55e'
                          }
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>

                {/* Legend */}
                <div className="flex gap-6 justify-center mt-2 text-xs text-gray-500">
                  <span className="flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded bg-red-500 inline-block"/>
                    Increased fraud risk
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded bg-green-500 inline-block"/>
                    Decreased fraud risk
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Plain English explanation */}
          {transaction.explanation_text && (
            <div className="mb-6">
              <h3 className="font-semibold text-gray-800 mb-3">
                Compliance Explanation
              </h3>
              <div className="bg-amber-50 border border-amber-200 rounded-lg
                              p-4 text-sm text-amber-800 leading-relaxed
                              whitespace-pre-line">
                {transaction.explanation_text}
              </div>
            </div>
          )}

          {/* Customer message */}
          {transaction.customer_message && !isAutoApproved && (
            <div className="mb-4">
              <h3 className="font-semibold text-gray-800 mb-2">
                Customer Message
              </h3>
              <div className="bg-gray-50 border border-gray-200 rounded-lg
                              p-4 text-sm text-gray-700">
                {transaction.customer_message}
              </div>
            </div>
          )}

          {/* Analyst action */}
          {transaction.analyst_action && !isAutoApproved && (
            <div>
              <h3 className="font-semibold text-gray-800 mb-2">
                Recommended Analyst Action
              </h3>
              <div className="bg-blue-50 border border-blue-200 rounded-lg
                              p-4 text-sm text-blue-800">
                {transaction.analyst_action}
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  )
}