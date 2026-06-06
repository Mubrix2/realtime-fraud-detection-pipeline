// frontend/src/components/TransactionTable.jsx
import RiskBadge from './RiskBadge'
import ActionBadge from './ActionBadge'

export default function TransactionTable({ transactions, selected, onSelect }) {
  if (transactions.length === 0) {
    return (
      <div className="text-center py-16 text-gray-400">
        <p className="text-lg">No transactions yet</p>
        <p className="text-sm mt-1">
          Submit a transaction using the form above
        </p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200">
            <th className="text-left px-4 py-3 font-medium text-gray-600">
              Transaction ID
            </th>
            <th className="text-left px-4 py-3 font-medium text-gray-600">
              Type
            </th>
            <th className="text-right px-4 py-3 font-medium text-gray-600">
              Amount (₦)
            </th>
            <th className="text-center px-4 py-3 font-medium text-gray-600">
              Action
            </th>
            <th className="text-center px-4 py-3 font-medium text-gray-600">
              Risk
            </th>
            <th className="text-right px-4 py-3 font-medium text-gray-600">
              Fraud Prob
            </th>
            <th className="text-center px-4 py-3 font-medium text-gray-600">
              Anomaly
            </th>
            <th className="text-right px-4 py-3 font-medium text-gray-600">
              ms
            </th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((tx) => {
            const isSelected =
              selected?.transaction_id === tx.transaction_id

            // Row colour based on action — not just is_flagged
            const rowBg =
              tx.action === 'BLOCK'
                ? 'bg-red-50 hover:bg-red-100'
                : tx.action === 'CHALLENGE'
                ? 'bg-orange-50 hover:bg-orange-100'
                : tx.action === 'FLAG'
                ? 'bg-yellow-50 hover:bg-yellow-100'
                : 'bg-white hover:bg-gray-50'

            // Auto-approved transactions (outside model scope)
            const isAutoApproved =
              tx.note?.includes('Auto-approved') ||
              tx.fraud_probability === 0.0 &&
              tx.action === 'APPROVE' &&
              !tx.explanation_available

            return (
              <tr
                key={tx.transaction_id}
                onClick={() => onSelect(tx)}
                className={`
                  border-b border-gray-100 cursor-pointer transition-colors
                  ${rowBg}
                  ${isSelected ? 'ring-2 ring-inset ring-blue-400' : ''}
                `}
              >
                <td className="px-4 py-3 font-mono text-xs text-gray-500">
                  {tx.transaction_id.slice(0, 16)}…
                </td>
                <td className="px-4 py-3 text-gray-700">
                  {tx.transaction?.type ?? '—'}
                </td>
                <td className="px-4 py-3 text-right font-medium">
                  {Number(tx.transaction?.amount ?? 0).toLocaleString()}
                </td>
                <td className="px-4 py-3 text-center">
                  <ActionBadge action={tx.action} />
                </td>
                <td className="px-4 py-3 text-center">
                  {isAutoApproved
                    ? <span className="text-xs text-gray-400 italic">
                        out of scope
                      </span>
                    : <RiskBadge level={tx.risk_level} />
                  }
                </td>
                <td className="px-4 py-3 text-right">
                  {isAutoApproved
                    ? <span className="text-xs text-gray-400">—</span>
                    : <span className={
                        tx.fraud_probability > 0.8
                          ? 'text-red-600 font-semibold'
                          : tx.fraud_probability > 0.6
                          ? 'text-orange-500 font-medium'
                          : 'text-gray-600'
                      }>
                        {(tx.fraud_probability * 100).toFixed(1)}%
                      </span>
                  }
                </td>
                <td className="px-4 py-3 text-center text-xs text-gray-500">
                  {tx.anomaly_severity}
                </td>
                <td className="px-4 py-3 text-right text-gray-400 text-xs">
                  {tx.processing_time_ms?.toFixed(0) ?? '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}