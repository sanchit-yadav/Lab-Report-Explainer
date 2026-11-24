import React, { useState, useEffect, useRef } from 'react'
import {
  Upload, FileText, Trash2, RefreshCw, CheckCircle2, AlertTriangle, 
  AlertCircle, Download, Send, Search, Filter, Languages, Sparkles, 
  ChevronRight, ArrowLeft, Loader2, User, ExternalLink, Dna, PlusCircle
} from 'lucide-react'
import { RangeGauge } from './RangeGauge'

const SAMPLE_OPTIONS = [
  { label: 'SRL Lipid Panel (Lipid Profile)', file: 'srl_lipid_panel.pdf' },
  { label: 'Thyrocare CBC (Complete Blood Count)', file: 'thyrocare_cbc.pdf' },
  { label: 'Metropolis Liver Function Test (LFT)', file: 'metropolis_liver.pdf' },
  { label: 'Thyrocare Kidney Function Test (KFT)', file: 'thyrocare_kidney.pdf' },
  { label: 'SRL Diabetes & Glycemic Panel', file: 'srl_diabetes.pdf' },
  { label: 'Dr. Lal PathLabs Thyroid Profile', file: 'lal_pathlabs_thyroid.pdf' },
  { label: 'Max Healthcare Full Body Checkup (Multi-Page)', file: 'multipage_full_body.pdf' },
  { label: 'Apollo Diagnostics Serology (Non-Numeric)', file: 'non_numeric.pdf' },
]

export function Dashboard({ user, client, onLogout }) {
  // Navigation / Workspace state
  const [reportsHistory, setReportsHistory] = useState([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [activeJobId, setActiveJobId] = useState(null)
  const [jobStatus, setJobStatus] = useState(null)
  const [statusMessage, setStatusMessage] = useState('')
  const [progressPct, setProgressPct] = useState(0)

  // Preferences
  const [language, setLanguage] = useState('en')
  const [humanReviewMode, setHumanReviewMode] = useState(true)
  const [explainAll, setExplainAll] = useState(false)

  // Ingestion / Upload state
  const [selectedFile, setSelectedFile] = useState(null)
  const [selectedSample, setSelectedSample] = useState('')
  const [isUploading, setIsUploading] = useState(false)
  const [uploadError, setUploadError] = useState(null)

  // Step 2 HITL state
  const [extractedData, setExtractedData] = useState(null)
  const [patientNameInput, setPatientNameInput] = useState('')
  const [editableTests, setEditableTests] = useState([])
  const [isConfirming, setIsConfirming] = useState(false)

  // Step 3 Findings state
  const [explanation, setExplanation] = useState(null)
  const [biomarkerFilter, setBiomarkerFilter] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [isDownloadingPdf, setIsDownloadingPdf] = useState(false)

  // Q&A Chat state
  const [chatMessages, setChatMessages] = useState([])
  const [chatInput, setChatInput] = useState('')
  const [isAnsweringChat, setIsAnsweringChat] = useState(false)

  const pollingTimerRef = useRef(null)
  // Incrementing this triggers the polling effect to restart (e.g. after HITL confirm)
  const [pollingTrigger, setPollingTrigger] = useState(0)

  // Fetch report history on mount
  useEffect(() => {
    fetchHistory()
    return () => {
      if (pollingTimerRef.current) clearInterval(pollingTimerRef.current)
    }
  }, [])

  const fetchHistory = async () => {
    try {
      setLoadingHistory(true)
      const data = await client.listReports(25)
      setReportsHistory(data || [])
    } catch {
      // quiet fail
    } finally {
      setLoadingHistory(false)
    }
  }

  // Poll Job Status when activeJobId is in-progress
  useEffect(() => {
    if (!activeJobId) return

    let consecutiveErrors = 0
    const poll = async () => {
      try {
        const res = await client.getJobStatus(activeJobId)
        consecutiveErrors = 0
        setJobStatus(res.status)
        setProgressPct(res.progress_pct || 15)
        setStatusMessage(res.current_step || 'Processing report...')

        if (res.status === 'ready') {
          clearInterval(pollingTimerRef.current)
          loadExplanation(activeJobId)
          fetchHistory()
        } else if (res.status === 'review_needed') {
          clearInterval(pollingTimerRef.current)
          loadExtractedForReview(activeJobId)
        } else if (res.status === 'failed') {
          clearInterval(pollingTimerRef.current)
          setUploadError(res.error || 'Pipeline execution failed.')
        }
      } catch (err) {
        consecutiveErrors++
        if (consecutiveErrors >= 5) {
          clearInterval(pollingTimerRef.current)
          setUploadError('Lost connection to server. Please refresh and try again.')
        }
      }
    }

    poll()
    pollingTimerRef.current = setInterval(poll, 1500)

    return () => {
      if (pollingTimerRef.current) clearInterval(pollingTimerRef.current)
    }
  }, [activeJobId, pollingTrigger])

  const loadExplanation = async (jobId) => {
    try {
      const exp = await client.getExplanation(jobId)
      setExplanation(exp)
    } catch (err) {
      setUploadError(err.message)
    }
  }

  const loadExtractedForReview = async (jobId) => {
    try {
      const ext = await client.getExtractedReport(jobId)
      setExtractedData(ext)
      setPatientNameInput(ext.patient_name || 'Patient')
      setEditableTests(ext.tests || [])
    } catch (err) {
      setUploadError(err.message)
    }
  }

  const handleStartAnalysis = async () => {
    setUploadError(null)
    setIsUploading(true)

    try {
      let fileToUpload = selectedFile

      // If sample selected instead of uploaded file, fetch sample bytes from sample endpoint or create blob
      if (!fileToUpload && selectedSample) {
        // We will pass the sample filename; in our API, upload accepts multipart file
        const sampleOpt = SAMPLE_OPTIONS.find((s) => s.file === selectedSample)
        if (sampleOpt) {
          // Fetch sample through frontend or dummy blob with name
          // For real files on disk, we upload a dummy file with that filename so backend loads it
          const res = await fetch(`/data/sample_reports/${selectedSample}`).catch(() => null)
          if (res && res.ok) {
            const blob = await res.blob()
            fileToUpload = new File([blob], selectedSample, { type: 'application/pdf' })
          } else {
            // Fallback: create empty named PDF file, backend will match by filename
            fileToUpload = new File(['%PDF-1.4 sample'], selectedSample, { type: 'application/pdf' })
          }
        }
      }

      if (!fileToUpload) {
        setUploadError('Please select a file or clinical sample to begin.')
        setIsUploading(false)
        return
      }

      const autoConfirm = !humanReviewMode
      const res = await client.uploadReport(fileToUpload, explainAll, autoConfirm)
      setActiveJobId(res.job_id)
      setJobStatus(res.status)
      setExplanation(null)
      setExtractedData(null)
      setChatMessages([])
    } catch (err) {
      setUploadError(err.message || 'Upload failed.')
    } finally {
      setIsUploading(false)
    }
  }

  const handleConfirmReview = async (skipEditing = false) => {
    const testsToSubmit = skipEditing ? extractedData?.tests : editableTests
    if (!testsToSubmit || testsToSubmit.length === 0) {
      setUploadError('No test parameters to confirm. Please check the extracted report.')
      return
    }
    setIsConfirming(true)
    try {
      await client.confirmReport(activeJobId, testsToSubmit, patientNameInput, explainAll)
      setJobStatus('flagging')
      setStatusMessage('Synthesizing clinical explanations...')
      // Restart status polling — the polling useEffect only fires on activeJobId changes,
      // so we bump pollingTrigger to re-subscribe after the HITL confirm step
      setPollingTrigger(t => t + 1)
    } catch (err) {
      setUploadError(err.message || 'Failed to submit verified parameters.')
    } finally {
      setIsConfirming(false)
    }
  }

  const handleLoadJob = async (jobId, status) => {
    setActiveJobId(jobId)
    setJobStatus(status)
    setExplanation(null)
    setExtractedData(null)
    setChatMessages([])
    setUploadError(null)

    if (status === 'ready') {
      await loadExplanation(jobId)
    } else if (status === 'review_needed') {
      await loadExtractedForReview(jobId)
    }
  }

  const handleDeleteJob = async (e, jobId) => {
    e.stopPropagation()
    try {
      await client.deleteReport(jobId)
      if (activeJobId === jobId) {
        setActiveJobId(null)
        setJobStatus(null)
        setExplanation(null)
        setExtractedData(null)
      }
      fetchHistory()
    } catch (err) {
      alert(`Delete failed: ${err.message}`)
    }
  }

  const handleDownloadPdf = async () => {
    if (!activeJobId) return
    setIsDownloadingPdf(true)
    try {
      const blob = await client.downloadPdf(activeJobId)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Doctor_Brief_${activeJobId.substring(0, 8)}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      alert(`PDF download failed: ${err.message}`)
    } finally {
      setIsDownloadingPdf(false)
    }
  }

  const handleSendChat = async (e) => {
    e.preventDefault()
    if (!chatInput.trim() || !activeJobId || isAnsweringChat) return

    const query = chatInput.trim()
    setChatInput('')
    const updatedHistory = [...chatMessages, { role: 'user', content: query }]
    setChatMessages(updatedHistory)
    setIsAnsweringChat(true)

    try {
      const res = await client.askQuestion(activeJobId, query, updatedHistory.slice(-6))
      const answer = language === 'hi' ? (res.answer_hi || res.answer_en) : res.answer_en
      const fullReply = `${answer}\n\n*${res.disclaimer || ''}*`
      setChatMessages((prev) => [
        ...prev,
        { role: 'assistant', content: fullReply, sources: res.source_urls || [] },
      ])
    } catch (err) {
      setChatMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Sorry, I could not answer that: ${err.message}` },
      ])
    } finally {
      setIsAnsweringChat(false)
    }
  }

  // Filtered Biomarkers for display
  const testExplanations = explanation?.test_explanations || []
  const filteredTests = testExplanations.filter((t) => {
    const flag = (t.flag || 'unknown').toLowerCase()
    if (biomarkerFilter === 'abnormal' && (flag === 'normal' || flag === 'unknown')) return false
    if (biomarkerFilter === 'normal' && flag !== 'normal') return false
    if (searchQuery && !t.test_name?.toLowerCase().includes(searchQuery.toLowerCase())) return false
    return true
  })

  return (
    <div className="min-h-screen bg-slate-50 flex">
      
      {/* Sidebar: Deep Slate (#0f172a) */}
      <aside className="w-80 bg-slate-900 text-white shrink-0 border-r border-slate-800 flex flex-col justify-between hidden md:flex">
        <div>
          {/* Brand & User Profile */}
          <div className="p-5 border-b border-slate-800">
            <div className="flex items-center gap-2.5 mb-4">
              <div className="w-8 h-8 rounded-lg bg-teal-500/10 border border-teal-500/30 text-teal-400 flex items-center justify-center">
                <Dna className="w-4 h-4" />
              </div>
              <div>
                <div className="text-sm font-black tracking-tight text-white">LabExplainer</div>
                <div className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">Clinical Workspace</div>
              </div>
            </div>

            <div className="bg-slate-800/60 rounded-xl p-3 border border-slate-700/60 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center text-xs font-bold text-teal-300">
                  {user?.full_name ? user.full_name[0].toUpperCase() : 'U'}
                </div>
                <div>
                  <div className="text-xs font-bold text-white truncate max-w-[130px]">
                    {user?.full_name || user?.email}
                  </div>
                  <div className="text-[10px] uppercase font-bold text-teal-400 tracking-wider">
                    Patient
                  </div>
                </div>
              </div>
              <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/50" />
            </div>
          </div>

          {/* New Analysis Action */}
          <div className="p-4 border-b border-slate-800">
            <button
              onClick={() => {
                setActiveJobId(null)
                setJobStatus(null)
                setExplanation(null)
                setExtractedData(null)
                setChatMessages([])
                setSelectedFile(null)
                setSelectedSample('')
              }}
              className="w-full py-2.5 px-3 rounded-xl bg-teal-600 hover:bg-teal-500 text-white text-xs font-bold flex items-center justify-center gap-2 shadow-sm transition cursor-pointer"
            >
              <PlusCircle className="w-4 h-4" />
              Analyze New Report
            </button>
          </div>

          {/* Reports History List */}
          <div className="p-4">
            <div className="flex items-center justify-between mb-3 text-xs font-bold text-slate-400 uppercase tracking-wider">
              <span>My Reports</span>
              <button onClick={fetchHistory} className="hover:text-white transition">
                <RefreshCw className={`w-3.5 h-3.5 ${loadingHistory ? 'animate-spin' : ''}`} />
              </button>
            </div>

            <div className="space-y-1.5 max-h-[300px] overflow-y-auto pr-1">
              {reportsHistory.length === 0 ? (
                <div className="text-xs text-slate-500 py-4 text-center italic">
                  No previous reports found.
                </div>
              ) : (
                reportsHistory.map((rep) => {
                  const isActive = rep.job_id === activeJobId
                  const isReady = rep.status === 'ready'
                  return (
                    <div
                      key={rep.job_id}
                      onClick={() => handleLoadJob(rep.job_id, rep.status)}
                      className={`p-2.5 rounded-xl border transition flex items-center justify-between cursor-pointer group ${
                        isActive
                          ? 'bg-slate-800 border-teal-500/50 text-white'
                          : 'bg-slate-900/40 border-slate-800 text-slate-300 hover:bg-slate-800/40'
                      }`}
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <span className={`w-2 h-2 rounded-full shrink-0 ${isReady ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                        <div className="min-w-0">
                          <div className="text-xs font-bold truncate max-w-[160px]">
                            {rep.filename || 'Report.pdf'}
                          </div>
                          <div className="text-[10px] text-slate-400">
                            {rep.patient_name || (rep.created_at || '').substring(0, 10)}
                          </div>
                        </div>
                      </div>

                      <button
                        onClick={(e) => handleDeleteJob(e, rep.job_id)}
                        title="Delete report"
                        className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-rose-500/20 hover:text-rose-400 text-slate-400 transition"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </div>

        {/* Sidebar Footer: Preferences & Sign Out */}
        <div className="p-4 border-t border-slate-800 space-y-3 bg-slate-950/40">
          <div className="flex items-center justify-between text-xs text-slate-300">
            <span className="font-semibold flex items-center gap-1.5">
              <Languages className="w-3.5 h-3.5 text-teal-400" /> Language
            </span>
            <div className="inline-flex rounded-lg border border-slate-700 p-0.5 bg-slate-800 text-[11px]">
              <button
                onClick={() => setLanguage('en')}
                className={`px-2 py-0.5 rounded font-semibold ${language === 'en' ? 'bg-teal-600 text-white' : 'text-slate-400'}`}
              >
                EN
              </button>
              <button
                onClick={() => setLanguage('hi')}
                className={`px-2 py-0.5 rounded font-semibold ${language === 'hi' ? 'bg-teal-600 text-white' : 'text-slate-400'}`}
              >
                HI
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between text-xs text-slate-300">
            <span className="font-semibold text-[11px]">Human-in-the-Loop Review</span>
            <input
              type="checkbox"
              checked={humanReviewMode}
              onChange={(e) => setHumanReviewMode(e.target.checked)}
              className="rounded accent-teal-600 w-3.5 h-3.5"
            />
          </div>

          <button
            onClick={onLogout}
            className="w-full py-2 text-xs font-semibold text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition flex items-center justify-center gap-1.5"
          >
            Sign Out
          </button>
        </div>
      </aside>

      {/* Main Workspace Area */}
      <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 space-y-6">
        
        {/* Workspace Top Header */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-black text-slate-900 tracking-tight">
              {language === 'hi' ? `नमस्ते, ${user?.full_name || 'उपयोगकर्ता'}` : `Welcome back, ${user?.full_name || 'Patient'}`}
            </h1>
            <p className="text-xs text-slate-500 mt-1">
              Clinical Decision Support • Deterministic Reference Range Flagging & MedlinePlus Grounding
            </p>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs font-bold px-3 py-1 rounded-full bg-slate-100 text-slate-700 border border-slate-200 uppercase tracking-wider">
              Patient Portal
            </span>
            <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              Engine Online
            </span>
          </div>
        </div>

        {/* Clinical Disclaimer Banner */}
        <div className="bg-slate-50 border-l-4 border-teal-600 p-4 rounded-r-xl text-xs text-slate-700 leading-relaxed shadow-sm">
          <strong>⚠️ Clinical Notice:</strong> This platform is an educational diagnostic explainer and clinical decision support system. It does not provide medical diagnoses or prescribe medications. Always discuss your laboratory results with your licensed physician.
        </div>

        {/* ========================================================= */}
        {/* STATE 1: EMPTY STATE & INGESTION (Upload / Sample Select) */}
        {/* ========================================================= */}
        {(!activeJobId || jobStatus === null) && (
          <div className="bg-white rounded-2xl border border-slate-200 p-8 shadow-sm space-y-6">
            <div className="space-y-1">
              <h2 className="text-lg font-bold text-slate-900">Analyze Laboratory Report</h2>
              <p className="text-xs text-slate-500">
                Upload your digital laboratory document (PDF, PNG, JPG, JPEG, WEBP) or select a pre-loaded clinical sample.
              </p>
            </div>

            {uploadError && (
              <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs font-semibold text-rose-700">
                {uploadError}
              </div>
            )}

            <div className="grid md:grid-cols-12 gap-6 items-start">
              {/* Drag & Drop Upload Zone */}
              <div className="md:col-span-8">
                <label className="border-2 border-dashed border-slate-300 hover:border-slate-900 rounded-2xl p-8 flex flex-col items-center justify-center text-center cursor-pointer transition bg-slate-50/50 hover:bg-slate-50">
                  <div className="w-12 h-12 rounded-xl bg-teal-50 text-teal-600 flex items-center justify-center mb-3 shadow-sm">
                    <Upload className="w-6 h-6" />
                  </div>
                  <div className="text-sm font-bold text-slate-800">
                    {selectedFile ? selectedFile.name : 'Click or drag laboratory report here'}
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    Supports high-resolution digital PDFs, document scans, and photos up to 50MB
                  </p>
                  <input
                    type="file"
                    accept=".pdf,.png,.jpg,.jpeg,.webp"
                    onChange={(e) => {
                      if (e.target.files?.[0]) {
                        setSelectedFile(e.target.files[0])
                        setSelectedSample('')
                      }
                    }}
                    className="hidden"
                  />
                </label>
              </div>

              {/* Sample Selector */}
              <div className="md:col-span-4 bg-slate-50 rounded-2xl p-6 border border-slate-200 space-y-4">
                <div className="text-xs font-bold text-slate-800 uppercase tracking-wider">Or Choose a Sample:</div>
                <select
                  value={selectedSample}
                  onChange={(e) => {
                    setSelectedSample(e.target.value)
                    setSelectedFile(null)
                  }}
                  className="w-full text-xs font-medium bg-white border border-slate-300 rounded-xl p-2.5 focus:outline-none focus:ring-2 focus:ring-slate-900"
                >
                  <option value="">-- Choose Sample Report --</option>
                  {SAMPLE_OPTIONS.map((s, idx) => (
                    <option key={idx} value={s.file}>
                      {s.label}
                    </option>
                  ))}
                </select>

                <div className="text-[11px] text-slate-500 leading-relaxed">
                  Pre-loaded patient panels include complete blood counts, glycemic tests, lipid panels, and multi-page checkups.
                </div>
              </div>
            </div>

            <button
              onClick={handleStartAnalysis}
              disabled={isUploading || (!selectedFile && !selectedSample)}
              className="w-full py-3 text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 disabled:bg-slate-300 rounded-xl shadow-md transition flex items-center justify-center gap-2 cursor-pointer"
            >
              {isUploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4 text-teal-400" />}
              {isUploading ? 'Uploading to Clinical Engine...' : 'Analyze Lab Report'}
            </button>
          </div>
        )}

        {/* ========================================================= */}
        {/* STATE 2: ASYNCHRONOUS PROGRESS BAR & REAL POLLING         */}
        {/* ========================================================= */}
        {['queued', 'extracting', 'flagging', 'rag_retrieval', 'generating'].includes(jobStatus) && (
          <div className="bg-white rounded-2xl border border-slate-200 p-8 shadow-sm text-center space-y-4">
            <div className="w-12 h-12 rounded-xl bg-teal-50 text-teal-600 flex items-center justify-center mx-auto animate-pulse">
              <Loader2 className="w-6 h-6 animate-spin" />
            </div>
            <div className="space-y-1">
              <h3 className="text-base font-bold text-slate-900">Clinical Engine Pipeline Active</h3>
              <p className="text-xs text-slate-600 font-medium">{statusMessage}</p>
            </div>

            {/* Progress Bar */}
            <div className="w-full max-w-md mx-auto h-2 bg-slate-100 rounded-full overflow-hidden">
              <div
                style={{ width: `${progressPct}%` }}
                className="h-full bg-teal-600 transition-all duration-500 rounded-full"
              />
            </div>
            <div className="text-[11px] text-slate-400">{progressPct}% completed</div>
          </div>
        )}

        {/* ========================================================= */}
        {/* STATE 3: STEP 2 HUMAN-IN-THE-LOOP REVIEW EDITOR            */}
        {/* ========================================================= */}
        {jobStatus === 'review_needed' && extractedData && (
          <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-6">
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <div>
                <span className="text-xs font-bold text-teal-600 uppercase tracking-wider">Step 2 • Human-in-the-Loop</span>
                <h3 className="text-xl font-black text-slate-900">Inspect Extracted Parameters</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Verify or edit extracted test names, values, units, and reference intervals before generating clinical explanations.
                </p>
              </div>
            </div>

            {/* Patient Name input */}
            <div className="max-w-xs">
              <label className="block text-xs font-bold text-slate-700 mb-1">Patient Identifier</label>
              <input
                type="text"
                value={patientNameInput}
                onChange={(e) => setPatientNameInput(e.target.value)}
                className="w-full text-xs bg-slate-50 border border-slate-300 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-slate-900 font-medium"
              />
            </div>

            {/* Editable Parameter Table */}
            <div className="border border-slate-200 rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-700 font-bold uppercase text-[10px]">
                    <tr>
                      <th className="p-3">Biomarker Name</th>
                      <th className="p-3">Result Value</th>
                      <th className="p-3">Unit</th>
                      <th className="p-3">Ref Low</th>
                      <th className="p-3">Ref High</th>
                      <th className="p-3">Reference String</th>
                      <th className="p-3">Status Flag</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {editableTests.map((t, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/50">
                        <td className="p-2.5">
                          <input
                            type="text"
                            value={t.test_name}
                            onChange={(e) => {
                              const updated = [...editableTests]
                              updated[idx].test_name = e.target.value
                              setEditableTests(updated)
                            }}
                            className="w-full bg-transparent font-medium text-slate-900 focus:outline-none"
                          />
                        </td>
                        <td className="p-2.5">
                          <input
                            type="number"
                            step="any"
                            value={t.value !== null && t.value !== undefined ? t.value : ''}
                            onChange={(e) => {
                              const updated = [...editableTests]
                              updated[idx].value = e.target.value === '' ? null : Number(e.target.value)
                              setEditableTests(updated)
                            }}
                            className="w-20 bg-slate-50 border border-slate-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-slate-900"
                          />
                        </td>
                        <td className="p-2.5">
                          <input
                            type="text"
                            value={t.unit || ''}
                            onChange={(e) => {
                              const updated = [...editableTests]
                              updated[idx].unit = e.target.value
                              setEditableTests(updated)
                            }}
                            className="w-16 bg-transparent text-slate-600 focus:outline-none"
                          />
                        </td>
                        <td className="p-2.5">
                          <input
                            type="number"
                            step="any"
                            value={t.ref_low !== null && t.ref_low !== undefined ? t.ref_low : ''}
                            onChange={(e) => {
                              const updated = [...editableTests]
                              updated[idx].ref_low = e.target.value === '' ? null : Number(e.target.value)
                              setEditableTests(updated)
                            }}
                            className="w-16 bg-slate-50 border border-slate-200 rounded px-2 py-1 focus:outline-none"
                          />
                        </td>
                        <td className="p-2.5">
                          <input
                            type="number"
                            step="any"
                            value={t.ref_high !== null && t.ref_high !== undefined ? t.ref_high : ''}
                            onChange={(e) => {
                              const updated = [...editableTests]
                              updated[idx].ref_high = e.target.value === '' ? null : Number(e.target.value)
                              setEditableTests(updated)
                            }}
                            className="w-16 bg-slate-50 border border-slate-200 rounded px-2 py-1 focus:outline-none"
                          />
                        </td>
                        <td className="p-2.5 text-slate-500 font-mono text-[11px]">{t.ref_raw || '—'}</td>
                        <td className="p-2.5">
                          <select
                            value={t.flag || 'unknown'}
                            onChange={(e) => {
                              const updated = [...editableTests]
                              updated[idx].flag = e.target.value
                              setEditableTests(updated)
                            }}
                            className="text-xs bg-white border border-slate-200 rounded px-2 py-1 font-semibold uppercase"
                          >
                            <option value="normal">Normal</option>
                            <option value="high">High</option>
                            <option value="low">Low</option>
                            <option value="critical_high">Critical High</option>
                            <option value="critical_low">Critical Low</option>
                            <option value="unknown">Inconclusive</option>
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => handleConfirmReview(true)}
                disabled={isConfirming}
                className="px-4 py-2 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-xl transition"
              >
                Confirm As-Is (Skip Editing)
              </button>
              <button
                onClick={() => handleConfirmReview(false)}
                disabled={isConfirming}
                className="px-5 py-2 text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 rounded-xl shadow transition flex items-center gap-1.5"
              >
                {isConfirming && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                Confirm Parameters & Generate Explanations
              </button>
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* STATE 4: STEP 3 COMPLETE CLINICAL FINDINGS DASHBOARD      */}
        {/* ========================================================= */}
        {jobStatus === 'ready' && explanation && (
          <div className="space-y-6">
            
            {/* Critical Panic Alert Banner */}
            {explanation.panic_alerts && explanation.panic_alerts.length > 0 && (
              <div className="bg-rose-50 border-l-4 border-rose-600 p-5 rounded-r-xl shadow-sm space-y-1">
                <div className="flex items-center gap-2 text-rose-800 font-black text-sm">
                  <AlertTriangle className="w-5 h-5 text-rose-600" />
                  🚨 Critical Clinical Panic Alert Detected ({explanation.panic_alerts.length} Finding)
                </div>
                <p className="text-xs text-rose-900/90 leading-relaxed">
                  One or more laboratory analytes fall into clinically recognized critical panic intervals. Immediate medical evaluation by a licensed physician or emergency clinical care is strongly advised.
                </p>
              </div>
            )}

            {/* Top Diagnostic Metrics Row */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm text-center">
                <div className="text-3xl font-black text-slate-900">{explanation.total_tests || 0}</div>
                <div className="text-[11px] font-bold uppercase text-slate-500 tracking-wider mt-1">Total Analytes</div>
              </div>
              <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm text-center">
                <div className="text-3xl font-black text-emerald-600">
                  {Math.max(0, (explanation.total_tests || 0) - (explanation.flagged_count || 0))}
                </div>
                <div className="text-[11px] font-bold uppercase text-emerald-700 tracking-wider mt-1">In Normal Range</div>
              </div>
              <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm text-center">
                <div className="text-3xl font-black text-amber-600">{explanation.flagged_count || 0}</div>
                <div className="text-[11px] font-bold uppercase text-amber-700 tracking-wider mt-1">Abnormal / Flagged</div>
              </div>
              <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm text-center">
                <div className="text-3xl font-black text-rose-600">
                  {explanation.panic_alerts ? explanation.panic_alerts.length : 0}
                </div>
                <div className="text-[11px] font-bold uppercase text-rose-700 tracking-wider mt-1">Critical Alerts</div>
              </div>
            </div>

            {/* Executive Diagnostic Summary */}
            <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-teal-600" />
                  Executive Diagnostic Summary
                </h3>
              </div>
              <p className="text-xs text-slate-700 leading-relaxed whitespace-pre-line bg-slate-50 p-4 rounded-xl border border-slate-100">
                {language === 'hi' 
                  ? (explanation.report_summary_hi || explanation.report_summary_en) 
                  : explanation.report_summary_en}
              </p>
            </div>

            {/* Biomarker Analysis & Filters */}
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <h3 className="text-lg font-bold text-slate-900">Biomarker Analysis & Reference Ranges</h3>
                
                {/* Search & Filter Controls */}
                <div className="flex items-center gap-3">
                  <div className="relative">
                    <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
                    <input
                      type="text"
                      placeholder="Search biomarker..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="text-xs pl-8 pr-3 py-1.5 bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900"
                    />
                  </div>

                  <select
                    value={biomarkerFilter}
                    onChange={(e) => setBiomarkerFilter(e.target.value)}
                    className="text-xs bg-white border border-slate-300 rounded-lg px-2.5 py-1.5 font-semibold"
                  >
                    <option value="all">All Results</option>
                    <option value="abnormal">Flagged Abnormal Only</option>
                    <option value="normal">Normal Only</option>
                  </select>
                </div>
              </div>

              {/* Biomarker Cards Grid */}
              <div className="grid md:grid-cols-2 gap-4">
                {filteredTests.map((test, idx) => {
                  const flag = (test.flag || 'unknown').toLowerCase()
                  const isNormal = flag === 'normal'
                  const isCritical = flag.includes('critical')
                  const badgeColor = isNormal 
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200' 
                    : (isCritical ? 'bg-rose-50 text-rose-700 border-rose-200' : 'bg-amber-50 text-amber-700 border-amber-200')

                  const cleanExp = language === 'hi' ? (test.explanation_hi || test.explanation_en) : test.explanation_en

                  return (
                    <div key={idx} className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3 hover:border-slate-300 transition">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-900 text-sm">{test.test_name}</span>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase border ${badgeColor}`}>
                          {flag.toUpperCase()}
                        </span>
                      </div>

                      <div className="text-xs text-slate-600 flex items-center justify-between font-medium">
                        <span><strong>Result:</strong> {test.value} {test.unit || ''}</span>
                        <span><strong>Reference:</strong> {test.ref_raw || 'Standard Interval'}</span>
                      </div>

                      <RangeGauge
                        value={test.value}
                        refLow={test.ref_low}
                        refHigh={test.ref_high}
                        unit={test.unit}
                        flag={test.flag}
                      />

                      <div className="bg-slate-50 p-3 rounded-xl border-l-2 border-teal-500 text-xs text-slate-700 leading-relaxed whitespace-pre-line">
                        {cleanExp}
                      </div>

                      {test.doctor_questions && test.doctor_questions.length > 0 && (
                        <div className="text-[11px] text-slate-500">
                          <strong className="text-slate-700">Questions for Physician:</strong>
                          <ul className="list-disc pl-4 mt-0.5 space-y-0.5">
                            {test.doctor_questions.map((q, qIdx) => (
                              <li key={qIdx}>{q}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {test.source_urls && test.source_urls.length > 0 && (
                        <div className="pt-2 border-t border-slate-100 flex items-center gap-1.5 text-[10px] text-slate-400">
                          <ExternalLink className="w-3 h-3 text-teal-600" />
                          <a href={test.source_urls[0]} target="_blank" rel="noreferrer" className="text-teal-700 hover:underline truncate">
                            MedlinePlus Clinical Source
                          </a>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Doctor Discussion Preparation & PDF Download */}
            <div className="bg-slate-900 text-white rounded-2xl p-6 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-6">
              <div className="space-y-2 max-w-xl">
                <div className="text-xs font-bold text-teal-400 uppercase tracking-wider">Doctor Visit Preparation</div>
                <h4 className="text-lg font-black tracking-tight">Printable Doctor Discussion Brief PDF</h4>
                <p className="text-xs text-slate-300 leading-relaxed">
                  Download a professionally formatted clinical consultation brief summarizing all out-of-range biomarkers, optimal reference limits, and high-yield discussion questions for your physician.
                </p>
              </div>

              <button
                onClick={handleDownloadPdf}
                disabled={isDownloadingPdf}
                className="px-6 py-3 rounded-xl bg-teal-500 hover:bg-teal-400 text-slate-950 font-bold text-xs flex items-center gap-2 shadow-lg transition shrink-0 cursor-pointer"
              >
                {isDownloadingPdf ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                Download Doctor Brief PDF
              </button>
            </div>

            {/* Conversational Clinical Q&A */}
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
              <div className="border-b border-slate-100 pb-3">
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-teal-600" />
                  Ask Questions About Your Lab Report
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Ask educational questions regarding your test numbers, biological functions, and reference intervals.
                </p>
              </div>

              {/* Chat Messages Log */}
              <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
                {chatMessages.length === 0 ? (
                  <div className="text-xs text-slate-400 text-center py-6 italic">
                    No questions asked yet. Ask things like: "What does my elevated cholesterol level indicate?"
                  </div>
                ) : (
                  chatMessages.map((msg, idx) => (
                    <div
                      key={idx}
                      className={`flex gap-3 text-xs ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                      <div
                        className={`max-w-[80%] rounded-2xl p-3.5 leading-relaxed whitespace-pre-line ${
                          msg.role === 'user'
                            ? 'bg-slate-900 text-white rounded-br-sm'
                            : 'bg-slate-50 text-slate-800 border border-slate-200/80 rounded-bl-sm'
                        }`}
                      >
                        {msg.content}
                      </div>
                    </div>
                  ))
                )}
              </div>

              {/* Chat Input Bar */}
              <form onSubmit={handleSendChat} className="flex gap-2 pt-2 border-t border-slate-100">
                <input
                  type="text"
                  placeholder="Ask a question about your lab results..."
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  className="flex-1 text-xs bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2.5 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-900"
                />
                <button
                  type="submit"
                  disabled={isAnsweringChat || !chatInput.trim()}
                  className="px-4 py-2.5 text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 disabled:bg-slate-300 rounded-xl shadow transition flex items-center gap-1.5 cursor-pointer"
                >
                  {isAnsweringChat ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                  Ask
                </button>
              </form>
            </div>

          </div>
        )}

      </main>
    </div>
  )
}
