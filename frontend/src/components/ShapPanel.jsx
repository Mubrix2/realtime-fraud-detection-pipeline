// frontend/src/components/ShapPanel.jsx
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  Cell, ResponsiveContainer,
} from 'recharts'
import RiskBadge from './RiskBadge'
import ActionBadge from './ActionBadge'

export default function ShapPanel({ transaction, onClose }) {
  if (!transaction) return null

  const reasons = transaction.top_reasons ?? []
  const isAutoApproved =
    transaction.note?.includes('Auto-approved') ||
    (transaction.fraud_probability === 0.0 &&
     !transaction.explanation_available)

  const chartData = reasons.map(r => ({
    name: r.description.length > 28
      ? r.description.slice(0, 28) + '…'
      : r.description,
    value: r.shap_value,
    direction: r.direction,
  }))

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5
                    h-full flex flex-col overflow-y-auto">

      {/* Header */}
      <div className="flex justify-between items-start mb-4">
        <div>
          <h3 className="font-semibold text-gray-800 text-sm">
            Transaction Detail
          </h3>
          <p className="text-xs text-gray-400 font-mono mt-0.5">
            {transaction.transaction_id}
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 text-lg leading-none"
        >
          ✕
        </button>
      </div>

      {/* Auto-approved banner */}
      {isAutoApproved && (
        <div className="mb-4 px-3 py-2 bg-blue-50 border border-blue-200
                        rounded text-xs text-blue-700">
          <strong>Auto-approved</strong> — transaction type (
          {transaction.transaction?.type}) is outside the model's scoring
          scope. The model was trained on TRANSFER and CASH_OUT only.
        </div>
      )}

      {/* Summary grid */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="bg-gray-50 rounded p-3">
          <p className="text-xs text-gray-500 mb-1">Decision</p>
          <ActionBadge action={transaction.action} />
        </div>
        <div className="bg-gray-50 rounded p-3">
          <p className="text-xs text-gray-500 mb-1">Risk Level</p>
          {isAutoApproved
            ? <span className="text-xs text-gray-400 italic">
                out of scope
              </span>
            : <RiskBadge level={transaction.risk_level} />
          }
        </div>
        <div className="bg-gray-50 rounded p-3">
          <p className="text-xs text-gray-500">Fraud Probability</p>
          <p className={`text-xl font-bold mt-0.5 ${
            transaction.fraud_probability > 0.8
              ? 'text-red-600'
              : transaction.fraud_probability > 0.6
              ? 'text-orange-500'
              : 'text-green-600'
          }`}>
            {isAutoApproved
              ? '—'
              : `${(transaction.fraud_probability * 100).toFixed(1)}%`
            }
          </p>
        </div>
        <div className="bg-gray-50 rounded p-3">
          <p className="text-xs text-gray-500">Anomaly</p>
          <p className="text-sm font-semibold mt-0.5">
            {transaction.anomaly_severity}
          </p>
        </div>
        <div className="bg-gray-50 rounded p-3">
          <p className="text-xs text-gray-500">Amount</p>
          <p className="text-sm font-semibold mt-0.5">
            ₦{Number(transaction.transaction?.amount ?? 0).toLocaleString()}
          </p>
        </div>
        <div className="bg-gray-50 rounded p-3">
          <p className="text-xs text-gray-500">Type</p>
          <p className="text-sm font-semibold mt-0.5">
            {transaction.transaction?.type ?? '—'}
          </p>
        </div>
      </div>

      {/* SHAP chart — only for scored transactions */}
      {!isAutoApproved && chartData.length > 0 && (
        <>
          <p className="text-xs font-medium text-gray-600 mb-2">
            SHAP Feature Contributions
          </p>
          <div className="flex-1 min-h-0">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={chartData}
                layout="vertical"
                margin={{ top: 0, right: 16, bottom: 0, left: 8 }}
              >
                <XAxis
                  type="number"
                  tick={{ fontSize: 10 }}
                  tickFormatter={v => v.toFixed(2)}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fontSize: 10 }}
                  width={170}
                />
                <Tooltip
                  formatter={v => [v.toFixed(4), 'SHAP Value']}
                  contentStyle={{ fontSize: 11 }}
                />
                <Bar dataKey="value" radius={[0, 3, 3, 0]}>
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
          </div>

          <div className="flex gap-4 mt-2 text-xs text-gray-500">
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded-sm bg-red-500 inline-block"/>
              Increased risk
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded-sm bg-green-500 inline-block"/>
              Decreased risk
            </span>
          </div>
        </>
      )}

      {/* Explanation text */}
      {transaction.explanation_text && (
        <div className="mt-4 p-3 bg-amber-50 border border-amber-200
                        rounded text-xs text-amber-800 leading-relaxed">
          {transaction.explanation_text}
        </div>
      )}

      <p className="text-xs text-gray-400 mt-3">
        Processed in {transaction.processing_time_ms?.toFixed(1) ?? '—'}ms
      </p>
    </div>
  )
}