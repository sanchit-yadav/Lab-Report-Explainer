/**
 * API client for interacting with the FastAPI CDS Backend (:8000).
 */

const BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '').replace(/\/$/, '')

export class APIError extends Error {
  constructor(message, status = 500, detail = null) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

async function request(endpoint, options = {}) {
  const token = localStorage.getItem('access_token')
  const headers = {
    ...(options.headers || {}),
  }

  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${token}`
  }

  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }

  const url = endpoint.startsWith('http') ? endpoint : `${BASE_URL}${endpoint}`
  const response = await fetch(url, {
    ...options,
    headers,
  })

  if (!response.ok) {
    let errorDetail = response.statusText
    try {
      const errJson = await response.json()
      errorDetail = errJson.detail || errJson.message || response.statusText
    } catch {
      // response wasn't json
    }
    throw new APIError(errorDetail, response.status, errorDetail)
  }

  if (response.headers.get('content-type')?.includes('application/pdf')) {
    return await response.blob()
  }

  const contentType = response.headers.get('content-type')
  if (contentType && contentType.includes('application/json')) {
    return await response.json()
  }

  return await response.text()
}

export const api = {
  // Auth
  async login(email, password) {
    const data = await request('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
    if (data.access_token) {
      localStorage.setItem('access_token', data.access_token)
    }
    return data
  },

  async register(email, password, fullName, role = 'patient') {
    const data = await request('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        email,
        password,
        full_name: fullName,
        role,
      }),
    })
    if (data.access_token) {
      localStorage.setItem('access_token', data.access_token)
    }
    return data
  },

  async getMe() {
    return await request('/api/v1/auth/me')
  },

  logout() {
    localStorage.removeItem('access_token')
  },

  // Reports Ingestion & Status
  async uploadReport(file, explainAll = false, autoConfirm = true) {
    const formData = new FormData()
    formData.append('file', file)

    const params = new URLSearchParams({
      explain_all: String(explainAll),
      auto_confirm: String(autoConfirm),
    })

    return await request(`/api/v1/reports/upload?${params.toString()}`, {
      method: 'POST',
      body: formData,
    })
  },

  async getJobStatus(jobId) {
    return await request(`/api/v1/reports/${jobId}/status`)
  },

  async getExtractedReport(jobId) {
    return await request(`/api/v1/reports/${jobId}/extracted`)
  },

  async confirmReport(jobId, tests, patientName, explainAll = false) {
    return await request(`/api/v1/reports/${jobId}/confirm`, {
      method: 'POST',
      body: JSON.stringify({
        tests,
        patient_name: patientName,
        explain_all: explainAll,
      }),
    })
  },

  async getExplanation(jobId) {
    return await request(`/api/v1/reports/${jobId}/explanation`)
  },

  async downloadPdf(jobId) {
    return await request(`/api/v1/reports/${jobId}/pdf`)
  },

  async askQuestion(jobId, question, chatHistory = []) {
    return await request(`/api/v1/reports/${jobId}/qa`, {
      method: 'POST',
      body: JSON.stringify({
        question,
        chat_history: chatHistory,
      }),
    })
  },

  async listReports(limit = 25) {
    return await request(`/api/v1/reports/?limit=${limit}`)
  },

  async deleteReport(jobId) {
    return await request(`/api/v1/reports/${jobId}`, {
      method: 'DELETE',
    })
  },

  async checkHealth() {
    try {
      const res = await fetch('/healthz')
      return res.ok
    } catch {
      return false
    }
  },
}
