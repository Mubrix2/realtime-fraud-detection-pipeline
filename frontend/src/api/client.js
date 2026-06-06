// frontend/src/api/client.js
/**
 * API client for the Fraud Detection Service.
 * All HTTP calls go through this module — no fetch() scattered in components.
 * This makes it easy to add auth headers, error handling, or swap base URLs.
 */
import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || ''

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// Global error interceptor
api.interceptors.response.use(
  res => res,
  err => {
    console.error('API error:', err.response?.data || err.message)
    return Promise.reject(err)
  }
)

export const checkHealth = () =>
  api.get('/health').then(r => r.data)

export const submitTransaction = (transaction) =>
  api.post('/api/v1/transactions/submit', transaction).then(r => r.data)

export const getRecentTransactions = (limit = 50) =>
  api.get('/api/v1/transactions/recent', { params: { limit } }).then(r => r.data)

export const getTransactionResult = (transactionId) =>
  api.get(`/api/v1/transactions/results/${transactionId}`).then(r => r.data)

export const getSystemStats = () =>
  api.get('/api/v1/transactions/stats').then(r => r.data)