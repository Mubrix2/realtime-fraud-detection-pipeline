// frontend/src/components/SubmitForm.jsx
import { useState } from 'react'
import { submitTransaction } from '../api/client'

const PRESETS = {
  suspicious: {
    label: '🚨 Suspicious — Full drain to zero-balance account',
    data: {
      transaction_id: `TXN-SUSP-${Date.now()}`,
      step: 3,
      type: 'TRANSFER',
      amount: 750000,
      name_orig: 'C1234567890',
      oldbalance_org: 750000,
      newbalance_orig: 0,
      name_dest: 'C9876543210',
      oldbalance_dest: 0,
      newbalance_dest: 0,
    },
  },
  legitimate: {
    label: '✅ Legitimate — Partial transfer with balanced accounts',
    data: {
      transaction_id: `TXN-LEGIT-${Date.now()}`,
      step: 14,
      type: 'PAYMENT',
      amount: 25000,
      name_orig: 'C1111111111',
      oldbalance_org: 500000,
      newbalance_orig: 475000,
      name_dest: 'M2222222222',
      oldbalance_dest: 1000000,
      newbalance_dest: 1025000,
    },
  },
}

/**
 * Transaction submission form with presets for demo.
 * Allows manual submission for live pipeline testing.
 */
export default function SubmitForm({ onSubmitted }) {
  const [loading, setLoading] = useState(false)
  const [feedback, setFeedback] = useState(null)
  const [form, setForm] = useState({
    transaction_id: `TXN-${Date.now()}`,
    step: 10,
    type: 'TRANSFER',
    amount: '',
    name_orig: 'C1234567890',
    oldbalance_org: '',
    newbalance_orig: '',
    name_dest: 'C9876543210',
    oldbalance_dest: 0,
    newbalance_dest: '',
  })

  const loadPreset = (key) => {
    const preset = PRESETS[key].data
    setForm({ ...preset, transaction_id: `TXN-${key.toUpperCase()}-${Date.now()}` })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setFeedback(null)

    try {
      const payload = {
        ...form,
        step: Number(form.step),
        amount: Number(form.amount),
        oldbalance_org: Number(form.oldbalance_org),
        newbalance_orig: Number(form.newbalance_orig),
        oldbalance_dest: Number(form.oldbalance_dest),
        newbalance_dest: Number(form.newbalance_dest),
      }

      await submitTransaction(payload)
      setFeedback({ type: 'success', message: `Submitted ${payload.transaction_id}` })
      onSubmitted?.()

      // Reset ID for next submission
      setForm(f => ({
        ...f,
        transaction_id: `TXN-${Date.now()}`,
      }))
    } catch (err) {
      setFeedback({
        type: 'error',
        message: err.response?.data?.detail || 'Submission failed',
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5 mb-6">
      <h2 className="font-semibold text-gray-800 mb-3">Submit Transaction</h2>

      {/* Presets */}
      <div className="flex flex-wrap gap-2 mb-4">
        {Object.entries(PRESETS).map(([key, preset]) => (
          <button
            key={key}
            type="button"
            onClick={() => loadPreset(key)}
            className="text-xs px-3 py-1.5 rounded border border-gray-300
                       hover:bg-gray-50 text-gray-600 transition-colors"
          >
            {preset.label}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { key: 'transaction_id', label: 'Transaction ID', span: 2 },
          { key: 'amount', label: 'Amount (₦)', type: 'number' },
          { key: 'step', label: 'Step (hour)', type: 'number' },
          { key: 'oldbalance_org', label: 'Sender Balance Before', type: 'number' },
          { key: 'newbalance_orig', label: 'Sender Balance After', type: 'number' },
          { key: 'oldbalance_dest', label: 'Recipient Balance Before', type: 'number' },
          { key: 'newbalance_dest', label: 'Recipient Balance After', type: 'number' },
        ].map(({ key, label, type = 'text', span }) => (
          <div key={key} className={span ? `col-span-${span}` : ''}>
            <label className="block text-xs text-gray-500 mb-1">{label}</label>
            <input
              type={type}
              value={form[key]}
              onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
              className="w-full border border-gray-200 rounded px-2 py-1.5
                         text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
              required
              min={type === 'number' ? 0 : undefined}
            />
          </div>
        ))}

        <div>
          <label className="block text-xs text-gray-500 mb-1">Type</label>
          <select
            value={form.type}
            onChange={e => setForm(f => ({ ...f, type: e.target.value }))}
            className="w-full border border-gray-200 rounded px-2 py-1.5
                       text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
          >
            {['TRANSFER', 'PAYMENT',].map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>

        <div className="col-span-2 md:col-span-4 flex items-center gap-4">
          <button
            type="submit"
            disabled={loading}
            className="px-5 py-2 bg-blue-600 text-white rounded text-sm
                       font-medium hover:bg-blue-700 disabled:opacity-50
                       transition-colors"
          >
            {loading ? 'Submitting…' : 'Submit Transaction'}
          </button>

          {feedback && (
            <p className={`text-sm ${
              feedback.type === 'success' ? 'text-green-600' : 'text-red-600'
            }`}>
              {feedback.message}
            </p>
          )}
        </div>
      </form>
    </div>
  )
}