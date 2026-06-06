// frontend/src/components/RiskBadge.jsx
/**
 * Colour-coded badge for transaction risk level.
 * Used in the transaction table and detail panel.
 */
const RISK_COLOURS = {
  CRITICAL: 'bg-red-100 text-red-800 border border-red-300',
  HIGH:     'bg-orange-100 text-orange-800 border border-orange-300',
  MEDIUM:   'bg-yellow-100 text-yellow-800 border border-yellow-300',
  LOW:      'bg-green-100 text-green-800 border border-green-300',
  UNKNOWN:  'bg-gray-100 text-gray-600 border border-gray-300',
}

export default function RiskBadge({ level }) {
  const colour = RISK_COLOURS[level] || RISK_COLOURS.UNKNOWN
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${colour}`}>
      {level}
    </span>
  )
}