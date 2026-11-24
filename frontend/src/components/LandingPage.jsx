import React, { useState } from 'react'
import { 
  ArrowRight, CheckCircle2, ShieldCheck, FileText, Cpu, BookOpen, 
  Languages, FileSpreadsheet, ChevronDown, Sparkles
} from 'lucide-react'
import { RangeGauge } from './RangeGauge'

const DEMO_SAMPLES = {
  lipid: {
    name: 'SRL Lipid Panel (Lipid Profile)',
    patient: 'Pooja Patel',
    date: '14-Nov-2026',
    total: 5,
    flagged: 2,
    tests: [
      {
        test_name: 'Total Cholesterol',
        value: 240.0,
        unit: 'mg/dL',
        ref_low: null,
        ref_high: 200.0,
        ref_raw: '< 200.0 mg/dL',
        flag: 'high',
        exp_en: '• What It Measures: Total Cholesterol evaluates cumulative circulating lipid and lipoprotein particles in your bloodstream.\n• What This Finding Indicates: Your observed result is 240.0 mg/dL, categorized as HIGH against standard reference (< 200.0 mg/dL). Elevated levels reflect higher circulating lipid density.',
        exp_hi: '• यह जांच क्या मापती है: कुल कोलेस्ट्रॉल आपके रक्तप्रवाह में मौजूद समग्र लिपिड और लिपोप्रोटीन कणों की मात्रा को मापता है।\n• आपके परिणाम का क्या अर्थ है: आपका परिणाम 240.0 mg/dL है, जो संदर्भ सीमा (< 200.0 mg/dL) के अनुसार HIGH की श्रेणी में आता है।',
        questions: [
          'How does this total cholesterol level factor into my overall cardiovascular risk assessment?',
          'Are any follow-up tests, monitoring intervals, or dietary modifications recommended?'
        ],
        source: 'https://medlineplus.gov/cholesterol.html'
      },
      {
        test_name: 'Triglycerides',
        value: 195.0,
        unit: 'mg/dL',
        ref_low: null,
        ref_high: 150.0,
        ref_raw: '< 150.0 mg/dL',
        flag: 'high',
        exp_en: '• What It Measures: Triglycerides evaluate the primary chemical form of circulating fatty acids stored in body fat.\n• What This Finding Indicates: Your observed result is 195.0 mg/dL, categorized as HIGH against standard reference (< 150.0 mg/dL).',
        exp_hi: '• यह जांच क्या मापती है: ट्राइग्लिसराइड्स शरीर में संचित वसा और रक्त में मौजूद मुख्य वसायुक्त अम्लों के स्तर का मूल्यांकन करते हैं।\n• आपके परिणाम का क्या अर्थ है: आपका परिणाम 195.0 mg/dL है, जो संदर्भ सीमा (< 150.0 mg/dL) के अनुसार HIGH है।',
        questions: [
          'What metabolic or dietary factors might be contributing to elevated triglycerides?',
          'What timeline do you recommend for a repeat lipid evaluation?'
        ],
        source: 'https://medlineplus.gov/triglycerides.html'
      },
      {
        test_name: 'HDL Cholesterol',
        value: 48.0,
        unit: 'mg/dL',
        ref_low: 40.0,
        ref_high: null,
        ref_raw: '> 40.0 mg/dL',
        flag: 'normal',
        exp_en: '• What It Measures: HDL (High-Density Lipoprotein) measures "protective" cholesterol that transports excess lipids from tissues back to the liver.\n• What This Finding Indicates: Your observed result is 48.0 mg/dL, categorized as NORMAL (> 40.0 mg/dL).',
        exp_hi: '• यह जांच क्या मापती है: एचडीएल सुरक्षात्मक कोलेस्ट्रॉल है जो अतिरिक्त वसा को ऊतकों से वापस यकृत में स्थानांतरित करने का कार्य करता है।\n• आपके परिणाम का क्या अर्थ है: आपका परिणाम 48.0 mg/dL है, जो सामान्य सीमा में है।',
        questions: [
          'Is my current HDL level sufficient to maintain a balanced cholesterol ratio?',
          'What aerobic or lifestyle habits help support healthy protective HDL levels?'
        ],
        source: 'https://medlineplus.gov/hdlthegoodcholesterol.html'
      }
    ]
  },
  cbc: {
    name: 'Thyrocare CBC (Complete Blood Count)',
    patient: 'Kavita Rao',
    date: '10-Nov-2026',
    total: 12,
    flagged: 1,
    tests: [
      {
        test_name: 'Hemoglobin',
        value: 10.4,
        unit: 'g/dL',
        ref_low: 12.0,
        ref_high: 15.5,
        ref_raw: '12.0 - 15.5 g/dL',
        flag: 'low',
        exp_en: '• What It Measures: Hemoglobin is the iron-rich protein in red blood cells that transports oxygen from your lungs to tissues throughout your body.\n• What This Finding Indicates: Your observed result is 10.4 g/dL, categorized as LOW against standard interval (12.0 - 15.5 g/dL). Reduced levels indicate diminished oxygen-carrying capacity.',
        exp_hi: '• यह जांच क्या मापती है: हीमोग्लोबिन लाल रक्त कोशिकाओं में मौजूद वह प्रोटीन है जो फेफड़ों से शरीर के सभी अंगों तक ऑक्सीजन पहुंचाता है।\n• आपके परिणाम का क्या अर्थ है: आपका परिणाम 10.4 g/dL है, जो संदर्भ सीमा (12.0 - 15.5 g/dL) के अनुसार LOW है।',
        questions: [
          'Could nutritional factors such as iron, ferritin, or vitamin B12 levels be contributing to this finding?',
          'Would you recommend a peripheral blood smear or serum iron study?'
        ],
        source: 'https://medlineplus.gov/lab-tests/hemoglobin-test/'
      }
    ]
  },
  liver: {
    name: 'Metropolis Liver Function Test (LFT)',
    patient: 'Amit Saxena',
    date: '08-Nov-2026',
    total: 8,
    flagged: 1,
    tests: [
      {
        test_name: 'SGPT (ALT)',
        value: 68.0,
        unit: 'U/L',
        ref_low: null,
        ref_high: 45.0,
        ref_raw: '< 45.0 U/L',
        flag: 'high',
        exp_en: '• What It Measures: ALT (Alanine Aminotransferase) is an intracellular enzyme found predominantly in liver cells.\n• What This Finding Indicates: Your observed result is 68.0 U/L, categorized as HIGH against the reference range (< 45.0 U/L). Elevated levels indicate increased cellular leakage into the bloodstream.',
        exp_hi: '• यह जांच क्या मापती है: एएलटी (एसजीपीटी) मुख्य रूप से यकृत की कोशिकाओं में पाया जाने वाला एक महत्वपूर्ण एंजाइम है।\n• आपके परिणाम का क्या अर्थ है: आपका परिणाम 68.0 U/L है, जो संदर्भ सीमा (< 45.0 U/L) के अनुसार HIGH है।',
        questions: [
          'What metabolic or dietary factors might have influenced this ALT level?',
          'Do you recommend repeat liver panel testing or an ultrasound evaluation?'
        ],
        source: 'https://medlineplus.gov/lab-tests/alt-blood-test/'
      }
    ]
  }
}

export function LandingPage({ onNavigate }) {
  const [activeSampleKey, setActiveSampleKey] = useState('lipid')
  const [demoLang, setDemoLang] = useState('en')
  const [openFaqIndex, setOpenFaqIndex] = useState(null)

  const activeSample = DEMO_SAMPLES[activeSampleKey]

  const faqs = [
    {
      q: 'What types of reports can I upload?',
      a: 'You can upload routine blood tests, Complete Blood Counts (CBC), Lipid Profiles, Liver Function Tests (LFT), Kidney Function Tests (KFT), Glycemic / HbA1c panels, Thyroid profiles, and multi-page comprehensive checkups in PDF, PNG, JPG, JPEG, and WEBP formats up to 50MB.'
    },
    {
      q: 'How does the application explain laboratory results?',
      a: 'Our multi-tier engine extracts biomarker names, values, units, and printed reference ranges. It computes deterministic flags against laboratory-printed reference bounds, retrieves peer-reviewed guidance from MedlinePlus, and formats concise 2-bullet clinical explanations.'
    },
    {
      q: 'Can it diagnose medical conditions or prescribe medicine?',
      a: 'No. The platform strictly enforces clinical safety guardrails. It never provides medical diagnoses, never recommends medications or drugs, and never suggests dosages. It is strictly an educational clinical decision support tool.'
    },
    {
      q: 'Can I ask questions about my report?',
      a: 'Yes! An interactive clinical Q&A interface allows you to ask educational questions about your biomarkers, biological functions, and reference intervals. All answers are grounded strictly in your uploaded report and MedlinePlus literature.'
    },
    {
      q: 'Can I download a report summary for my doctor?',
      a: 'Yes. With one click, you can generate and download a clean, printable Doctor Discussion Brief PDF containing your biomarker overview, out-of-range findings, and recommended discussion questions for your physician.'
    }
  ]

  return (
    <div className="space-y-24 pb-20">
      
      {/* Hero Section */}
      <section className="pt-8 sm:pt-14">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid lg:grid-cols-12 gap-12 items-center">
            
            {/* Left Hero Content */}
            <div className="lg:col-span-6 space-y-6">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
                <Sparkles className="w-3.5 h-3.5 text-emerald-600" />
                Enterprise Clinical Decision Support
              </div>

              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-black text-slate-900 tracking-tight leading-[1.12]">
                Your Lab Reports, <br />
                <span className="text-teal-600">Easier to Understand.</span>
              </h1>

              <p className="text-lg text-slate-600 leading-relaxed max-w-xl">
                Upload your laboratory report and understand your test results through simple explanations, 
                reference ranges, and helpful medical information.
              </p>

              {/* CTAs */}
              <div className="flex flex-wrap items-center gap-4 pt-2">
                <button
                  onClick={() => onNavigate('register')}
                  className="px-6 py-3.5 text-sm font-bold text-white bg-slate-900 hover:bg-slate-800 rounded-xl shadow-lg shadow-slate-900/10 transition flex items-center gap-2 group cursor-pointer"
                >
                  Analyze My Report
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition" />
                </button>
                <a
                  href="#how-it-works"
                  className="px-5 py-3.5 text-sm font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-xl shadow-sm transition"
                >
                  See How It Works
                </a>
              </div>

              {/* Trust Checkmarks */}
              <div className="grid grid-cols-2 gap-3 pt-4 border-t border-slate-200/80">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
                  <CheckCircle2 className="w-4 h-4 text-teal-600 shrink-0" />
                  Multi-Tier OCR & Layout Extraction
                </div>
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
                  <CheckCircle2 className="w-4 h-4 text-teal-600 shrink-0" />
                  Pure Deterministic Flagging
                </div>
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
                  <CheckCircle2 className="w-4 h-4 text-teal-600 shrink-0" />
                  MedlinePlus Clinical Grounding
                </div>
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
                  <CheckCircle2 className="w-4 h-4 text-teal-600 shrink-0" />
                  100% Local SQLite Data Privacy
                </div>
              </div>
            </div>

            {/* Right Hero: Linear-Style Live Product Preview (Option B) */}
            <div className="lg:col-span-6">
              <div className="rounded-2xl border border-slate-200/90 bg-white shadow-2xl shadow-slate-900/10 overflow-hidden">
                
                {/* macOS Window Titlebar */}
                <div className="bg-slate-100/90 border-b border-slate-200 px-4 py-3 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-rose-500" />
                    <div className="w-3 h-3 rounded-full bg-amber-500" />
                    <div className="w-3 h-3 rounded-full bg-emerald-500" />
                  </div>
                  <div className="text-xs font-semibold text-slate-600 tracking-tight">
                    Synthetic Dashboard Preview • Live Interactive Demo
                  </div>
                  <div className="flex items-center gap-1.5 text-[11px] font-bold text-emerald-600">
                    <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                    Active
                  </div>
                </div>

                {/* Sample Selector & Language Toggle Bar */}
                <div className="p-4 bg-slate-50 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <label className="text-xs font-bold text-slate-700">Sample Panel:</label>
                    <select
                      value={activeSampleKey}
                      onChange={(e) => setActiveSampleKey(e.target.value)}
                      className="text-xs font-medium bg-white border border-slate-300 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-slate-900"
                    >
                      <option value="lipid">SRL Lipid Panel</option>
                      <option value="cbc">Thyrocare CBC</option>
                      <option value="liver">Metropolis Liver (LFT)</option>
                    </select>
                  </div>

                  <div className="inline-flex rounded-lg border border-slate-300 p-0.5 bg-white text-xs">
                    <button
                      onClick={() => setDemoLang('en')}
                      className={`px-2.5 py-1 rounded-md font-semibold transition ${demoLang === 'en' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:text-slate-900'}`}
                    >
                      English
                    </button>
                    <button
                      onClick={() => setDemoLang('hi')}
                      className={`px-2.5 py-1 rounded-md font-semibold transition ${demoLang === 'hi' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:text-slate-900'}`}
                    >
                      हिंदी
                    </button>
                  </div>
                </div>

                {/* Dashboard Metrics Row */}
                <div className="p-4 grid grid-cols-3 gap-3 bg-white">
                  <div className="bg-slate-50 rounded-xl p-3 border border-slate-100 text-center">
                    <div className="text-xl font-bold text-slate-900">{activeSample.total}</div>
                    <div className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Total Analytes</div>
                  </div>
                  <div className="bg-emerald-50/50 rounded-xl p-3 border border-emerald-100 text-center">
                    <div className="text-xl font-bold text-emerald-700">{activeSample.total - activeSample.flagged}</div>
                    <div className="text-[10px] uppercase font-bold text-emerald-600 tracking-wider">Normal Results</div>
                  </div>
                  <div className="bg-amber-50/50 rounded-xl p-3 border border-amber-100 text-center">
                    <div className="text-xl font-bold text-amber-700">{activeSample.flagged}</div>
                    <div className="text-[10px] uppercase font-bold text-amber-600 tracking-wider">Out-of-Range</div>
                  </div>
                </div>

                {/* Biomarker Demo Cards */}
                <div className="p-4 space-y-3 bg-slate-50/50 border-t border-slate-100 max-h-96 overflow-y-auto">
                  {activeSample.tests.map((test, idx) => (
                    <div key={idx} className="bg-white rounded-xl p-4 border border-slate-200/80 shadow-sm space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-900 text-sm">{test.test_name}</span>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${
                          test.flag === 'normal' 
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' 
                            : 'bg-amber-50 text-amber-700 border border-amber-200'
                        }`}>
                          {test.flag.toUpperCase()}
                        </span>
                      </div>

                      <div className="text-xs text-slate-600 flex items-center justify-between">
                        <span><strong>Result:</strong> {test.value} {test.unit}</span>
                        <span><strong>Reference:</strong> {test.ref_raw}</span>
                      </div>

                      <RangeGauge 
                        value={test.value}
                        refLow={test.ref_low}
                        refHigh={test.ref_high}
                        unit={test.unit}
                        flag={test.flag}
                      />

                      <div className="bg-slate-50 rounded-lg p-2.5 text-xs text-slate-700 border-l-2 border-teal-500 whitespace-pre-line leading-relaxed">
                        {demoLang === 'hi' ? test.exp_hi : test.exp_en}
                      </div>

                      <div className="text-[11px] text-slate-500">
                        <strong className="text-slate-700">Questions for Doctor:</strong>
                        <ul className="list-disc pl-4 mt-0.5 space-y-0.5">
                          {test.questions.map((q, qIdx) => (
                            <li key={qIdx}>{q}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  ))}
                </div>

              </div>
            </div>

          </div>
        </div>
      </section>

      {/* Section C: How It Works */}
      <section id="how-it-works" className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 scroll-mt-24">
        <div className="text-center max-w-2xl mx-auto mb-14 space-y-3">
          <div className="text-xs font-bold text-teal-600 uppercase tracking-wider">Seamless 3-Step Process</div>
          <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">How It Works</h2>
          <p className="text-sm text-slate-600">
            From raw laboratory document to structured, physician-aligned clinical clarity in three transparent steps.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-8">
          <div className="bg-white rounded-2xl p-7 border border-slate-200/80 shadow-sm hover:shadow-md transition space-y-4">
            <span className="text-xs font-bold px-2.5 py-1 rounded-md bg-slate-900 text-white">STEP 01</span>
            <div className="w-12 h-12 rounded-xl bg-teal-50 text-teal-600 flex items-center justify-center">
              <FileText className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-slate-900">1. Upload Your Report</h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              Upload a digital PDF, scan, or photo of your routine blood test, metabolic panel, or pathology report. Supports multi-page documents up to 50MB.
            </p>
          </div>

          <div className="bg-white rounded-2xl p-7 border border-slate-200/80 shadow-sm hover:shadow-md transition space-y-4">
            <span className="text-xs font-bold px-2.5 py-1 rounded-md bg-slate-900 text-white">STEP 02</span>
            <div className="w-12 h-12 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
              <Cpu className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-slate-900">2. Review Your Results</h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              Our multi-tier engine extracts biomarker names, numeric values, measurement units, and printed reference intervals with optional Human-in-the-Loop review.
            </p>
          </div>

          <div className="bg-white rounded-2xl p-7 border border-slate-200/80 shadow-sm hover:shadow-md transition space-y-4">
            <span className="text-xs font-bold px-2.5 py-1 rounded-md bg-slate-900 text-white">STEP 03</span>
            <div className="w-12 h-12 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
              <Sparkles className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-slate-900">3. Understand Your Report</h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              Read simple explanations, review abnormal results, visualize reference ranges on color-coded gauges, and prepare targeted questions for your doctor.
            </p>
          </div>
        </div>
      </section>

      {/* Section D: Core Features */}
      <section id="features" className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 scroll-mt-24">
        <div className="text-center max-w-2xl mx-auto mb-14 space-y-3">
          <div className="text-xs font-bold text-teal-600 uppercase tracking-wider">Enterprise Capabilities</div>
          <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">Core Product Features</h2>
          <p className="text-sm text-slate-600">
            Engineered to enterprise diagnostic standards with mathematical rigor and ethical healthcare guardrails.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm space-y-3">
            <div className="w-10 h-10 rounded-lg bg-slate-100 text-slate-800 flex items-center justify-center">
              <FileSpreadsheet className="w-5 h-5" />
            </div>
            <h3 className="font-bold text-slate-900 text-base">Smart Report Extraction</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Multi-tier layout parsing combining native PDF text analysis and OCR fallback to reliably extract biomarker names, values, units, and ranges.
            </p>
          </div>

          <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm space-y-3">
            <div className="w-10 h-10 rounded-lg bg-slate-100 text-slate-800 flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5" />
            </div>
            <h3 className="font-bold text-slate-900 text-base">Normal & Abnormal Result Identification</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Strict deterministic mathematical evaluation against printed laboratory intervals. High, Low, and Critical Panic thresholds verified without guessing.
            </p>
          </div>

          <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm space-y-3">
            <div className="w-10 h-10 rounded-lg bg-slate-100 text-slate-800 flex items-center justify-center">
              <Sparkles className="w-5 h-5" />
            </div>
            <h3 className="font-bold text-slate-900 text-base">Simple AI-Powered Explanations</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Structured 2-bullet physician-grade summaries explaining what each test measures and what your specific result indicates in plain language.
            </p>
          </div>

          <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm space-y-3">
            <div className="w-10 h-10 rounded-lg bg-slate-100 text-slate-800 flex items-center justify-center">
              <BookOpen className="w-5 h-5" />
            </div>
            <h3 className="font-bold text-slate-900 text-base">Medical Information References</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Every biomarker explanation is grounded strictly in peer-reviewed clinical guidelines from the National Library of Medicine (MedlinePlus).
            </p>
          </div>

          <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm space-y-3">
            <div className="w-10 h-10 rounded-lg bg-slate-100 text-slate-800 flex items-center justify-center">
              <Languages className="w-5 h-5" />
            </div>
            <h3 className="font-bold text-slate-900 text-base">English and Hindi Explanations</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Full bilingual toggle support. Switch seamlessly between English and Hindi with a single click for accessible family healthcare communication.
            </p>
          </div>

          <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm space-y-3">
            <div className="w-10 h-10 rounded-lg bg-slate-100 text-slate-800 flex items-center justify-center">
              <FileText className="w-5 h-5" />
            </div>
            <h3 className="font-bold text-slate-900 text-base">Doctor Discussion Summary</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Automated high-yield personalized questions for your physician appointment and a downloadable printable Doctor Discussion Brief PDF.
            </p>
          </div>
        </div>
      </section>

      {/* Section E: Safety & Trust */}
      <section id="safety" className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 scroll-mt-24">
        <div className="bg-slate-900 text-white rounded-3xl p-8 sm:p-12 shadow-xl space-y-8">
          <div className="max-w-3xl space-y-3">
            <div className="inline-flex items-center gap-2 text-xs font-bold text-teal-400 bg-teal-950/80 px-3 py-1 rounded-full border border-teal-800">
              <ShieldCheck className="w-4 h-4" />
              Safety, Privacy & Clinical Guardrails
            </div>
            <h2 className="text-3xl sm:text-4xl font-black tracking-tight">
              Understand Your Results. Make Informed Conversations Possible.
            </h2>
            <p className="text-sm text-slate-300 leading-relaxed">
              Our application is an educational decision support platform engineered around strict ethical boundaries and verifiable data protections.
            </p>
          </div>

          <div className="grid sm:grid-cols-2 gap-6 pt-4 border-t border-slate-800 text-sm">
            <div className="space-y-1">
              <h4 className="font-bold text-white flex items-center gap-2">
                <span className="text-teal-400 font-bold">•</span> Educational Explanations Only
              </h4>
              <p className="text-xs text-slate-400 leading-relaxed">
                The application provides educational explanations, not medical diagnoses or treatment regimens.
              </p>
            </div>

            <div className="space-y-1">
              <h4 className="font-bold text-white flex items-center gap-2">
                <span className="text-teal-400 font-bold">•</span> Objective Reference Ranges
              </h4>
              <p className="text-xs text-slate-400 leading-relaxed">
                Laboratory reference ranges printed by the analyzing facility are used to interpret reported values objectively.
              </p>
            </div>

            <div className="space-y-1">
              <h4 className="font-bold text-white flex items-center gap-2">
                <span className="text-teal-400 font-bold">•</span> Qualified Clinical Consultation
              </h4>
              <p className="text-xs text-slate-400 leading-relaxed">
                AI explanations are not medical diagnoses. Users should always consult qualified healthcare professionals for medical decisions.
              </p>
            </div>

            <div className="space-y-1">
              <h4 className="font-bold text-white flex items-center gap-2">
                <span className="text-teal-400 font-bold">•</span> Cryptographic Local Privacy
              </h4>
              <p className="text-xs text-slate-400 leading-relaxed">
                Patient records and extraction audit trails reside in your local SQLite database with SHA-256 Merkle hashes. Zero PHI is shared or sold.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Section F: Frequently Asked Questions */}
      <section id="faq" className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 scroll-mt-24 space-y-8">
        <div className="text-center space-y-2">
          <div className="text-xs font-bold text-teal-600 uppercase tracking-wider">Got Questions?</div>
          <h2 className="text-3xl font-extrabold text-slate-900 tracking-tight">Frequently Asked Questions</h2>
        </div>

        <div className="space-y-3">
          {faqs.map((faq, index) => {
            const isOpen = openFaqIndex === index
            return (
              <div key={index} className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
                <button
                  onClick={() => setOpenFaqIndex(isOpen ? null : index)}
                  className="w-full px-5 py-4 text-left flex items-center justify-between text-sm font-bold text-slate-900 hover:bg-slate-50 transition"
                >
                  <span>{faq.q}</span>
                  <ChevronDown className={`w-4 h-4 text-slate-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                </button>
                {isOpen && (
                  <div className="px-5 pb-4 text-xs text-slate-600 leading-relaxed border-t border-slate-100 pt-3">
                    {faq.a}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </section>

      {/* Section G: Final CTA & Footer */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 rounded-3xl p-10 sm:p-14 text-center text-white space-y-6 shadow-2xl">
          <h2 className="text-3xl sm:text-4xl font-black tracking-tight max-w-2xl mx-auto">
            Start Understanding Your Lab Reports Today.
          </h2>
          <p className="text-sm text-slate-300 max-w-xl mx-auto">
            Join patients making informed diagnostic conversations possible with intelligent clinical decision support.
          </p>
          <button
            onClick={() => onNavigate('register')}
            className="px-7 py-3.5 text-sm font-bold text-slate-900 bg-white hover:bg-slate-100 rounded-xl shadow-lg transition inline-flex items-center gap-2 cursor-pointer"
          >
            Get Started Free
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>

        {/* Footer */}
        <footer className="mt-16 pt-8 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-500">
          <div>
            <strong>AI Clinical Lab Report Explainer</strong> • Educational Clinical Decision Support Platform
          </div>
          <div className="flex gap-4">
            <a href="#how-it-works" className="hover:text-slate-900">How It Works</a>
            <a href="#features" className="hover:text-slate-900">Features</a>
            <a href="#safety" className="hover:text-slate-900">Safety & Trust</a>
            <a href="#faq" className="hover:text-slate-900">FAQ</a>
          </div>
        </footer>
      </section>

    </div>
  )
}
