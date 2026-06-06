// frontend/src/App.jsx
import { useState, useEffect, useCallback } from 'react'
import { checkHealth, getRecentTransactions, getSystemStats } from './api/client'
import StatsBar from './components/StatsBar'
import TransactionTable from './components/TransactionTable'
import ShapModal from './components/ShapModal'
import SubmitForm from './components/SubmitForm'

const REFRESH_INTERVAL_MS = 3000

export default function App() {
  const [transactions, setTransactions] = useState([])
  const [selected, setSelected] = useState(null)
  const [stats, setStats] = useState(null)
  const [apiHealthy, setApiHealthy] = useState(null)
  const [lastRefresh, setLastRefresh] = useState(null)
  const [error, setError] = useState(null)

  const fetchData = useCallback(async () => {
    try {
      const [recentData, statsData] = await Promise.all([
        getRecentTransactions(100),
        getSystemStats(),
      ])
      setTransactions(recentData.transactions || [])
      setStats(statsData)
      setLastRefresh(new Date())
      setError(null)
      setApiHealthy(true)
    } catch (err) {
      setError('Failed to fetch data from API')
      setApiHealthy(false)
    }
  }, [])

  useEffect(() => {
    checkHealth()
      .then(() => setApiHealthy(true))
      .catch(() => setApiHealthy(false))
    fetchData()
  }, [fetchData])

  useEffect(() => {
    const interval = setInterval(fetchData, REFRESH_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchData])

  // Update selected transaction when new data arrives
  useEffect(() => {
    if (selected) {
      const updated = transactions.find(
        t => t.transaction_id === selected.transaction_id
      )
      if (updated) setSelected(updated)
    }
  }, [transactions])

  return (
    <div className="min-h-screen bg-gray-50">

      {/* SHAP Modal — rendered above everything */}
      {selected && (
        <ShapModal
          transaction={selected}
          onClose={() => setSelected(null)}
        />
      )}

      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-screen-xl mx-auto flex justify-between items-center">
          <div>
            <h1 className="text-lg font-bold text-gray-900">
              Fraud Detection Dashboard
            </h1>
            <p className="text-xs text-gray-400 mt-0.5">
              Real-time • XGBoost + Isolation Forest • SHAP Explainability
            </p>
          </div>

          <div className="flex items-center gap-4">
            {lastRefresh && (
              <span className="text-xs text-gray-400">
                Updated {lastRefresh.toLocaleTimeString()}
              </span>
            )}
            <div className={`
              flex items-center gap-1.5 text-xs px-3 py-1 rounded-full
              ${apiHealthy
                ? 'bg-green-50 text-green-700'
                : apiHealthy === false
                  ? 'bg-red-50 text-red-600'
                  : 'bg-gray-100 text-gray-400'}
            `}>
              <span className={`w-1.5 h-1.5 rounded-full ${
                apiHealthy ? 'bg-green-500 animate-pulse' : 'bg-red-400'
              }`}/>
              {apiHealthy ? 'API Connected' : 'API Unreachable'}
            </div>
          </div>
        </div>
      </header>

      {/* Body — full width, no side panel split */}
      <main className="max-w-screen-xl mx-auto px-6 py-6">

        {error && (
          <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200
                          rounded text-sm text-red-700">
            {error}
          </div>
        )}

        <StatsBar stats={stats} transactions={transactions} />
        <SubmitForm onSubmitted={fetchData} />

        <div className="flex justify-between items-center mb-3">
          <h2 className="font-semibold text-gray-700">
            Recent Transactions
            <span className="ml-2 text-sm font-normal text-gray-400">
              ({transactions.length})
            </span>
          </h2>
          <span className="text-xs text-gray-400">
            Click a row to see SHAP explanation
          </span>
        </div>

        <TransactionTable
          transactions={transactions}
          selected={selected}
          onSelect={setSelected}
        />
      </main>
    </div>
  )
}