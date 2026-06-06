// frontend/src/components/ActionBadge.jsx
const ACTION_STYLES = {
  BLOCK:     'bg-red-100 text-red-800 border border-red-300',
  CHALLENGE: 'bg-orange-100 text-orange-800 border border-orange-300',
  FLAG:      'bg-yellow-100 text-yellow-800 border border-yellow-300',
  APPROVE:   'bg-green-100 text-green-800 border border-green-300',
}

const ACTION_ICONS = {
  BLOCK:     '🚫',
  CHALLENGE: '⚠️',
  FLAG:      '🔍',
  APPROVE:   '✅',
}

export default function ActionBadge({ action }) {
  const style = ACTION_STYLES[action] || 'bg-gray-100 text-gray-600'
  const icon = ACTION_ICONS[action] || '—'
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${style}`}>
      {icon} {action}
    </span>
  )
}