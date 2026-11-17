import React from 'react'

export function RangeGauge({ value, refLow, refHigh, unit, flag }) {
  if (value === null || value === undefined || (refLow === null && refHigh === null)) {
    return null
  }

  const val = Number(value)
  const low = refLow !== null && refLow !== undefined ? Number(refLow) : null
  const high = refHigh !== null && refHigh !== undefined ? Number(refHigh) : null

  // Two-sided range [low, high]
  if (low !== null && high !== null && high > low) {
    const span = high - low
    let dMin = Math.max(0.0, low - span * 0.6)
    let dMax = high + span * 0.6
    if (val < dMin) dMin = Math.max(0.0, val * 0.85)
    if (val > dMax) dMax = val * 1.15

    const total = dMax - dMin
    if (total <= 0) return null

    const pLow = Math.max(5.0, ((low - dMin) / total) * 100)
    const pNorm = Math.max(10.0, ((high - low) / total) * 100)
    const pHigh = Math.max(5.0, 100.0 - pLow - pNorm)
    const pVal = Math.max(2.0, Math.min(97.0, ((val - dMin) / total) * 100))

    let markerColor = '#10b981' // emerald
    if (flag?.includes('critical')) {
      markerColor = '#ef4444' // red
    } else if (flag?.includes('high') || flag?.includes('low')) {
      markerColor = '#f59e0b' // amber
    }

    return (
      <div className="my-3 px-1">
        <div className="flex justify-between text-[11px] font-medium text-slate-500 mb-1.5">
          <span>Min: {dMin.toFixed(1)}</span>
          <span className="text-emerald-700 font-semibold bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
            Optimal: {low} - {high} {unit}
          </span>
          <span>Max: {dMax.toFixed(1)}</span>
        </div>
        
        {/* Track Bar */}
        <div className="relative h-3 bg-slate-200 rounded-full flex overflow-visible">
          <div
            style={{ width: `${pLow}%` }}
            className="bg-amber-200 rounded-l-full"
            title={`Low zone (< ${low})`}
          />
          <div
            style={{ width: `${pNorm}%` }}
            className="bg-emerald-300"
            title={`Normal range (${low} - ${high})`}
          />
          <div
            style={{ width: `${pHigh}%` }}
            className="bg-rose-200 rounded-r-full"
            title={`High zone (> ${high})`}
          />

          {/* Pointer Marker */}
          <div
            style={{ left: `${pVal}%`, backgroundColor: markerColor }}
            className="absolute -top-1 w-1.5 h-5 rounded-full border-2 border-white shadow-md transform -translate-x-1/2 z-10 transition-all duration-300"
            title={`Your result: ${val} ${unit}`}
          />
        </div>

        {/* Marker Label */}
        <div className="relative h-4 mt-1">
          <span
            style={{ left: `${pVal}%`, color: markerColor }}
            className="absolute transform -translate-x-1/2 text-[11px] font-bold tracking-tight whitespace-nowrap"
          >
            ▲ {val} {unit}
          </span>
        </div>
      </div>
    )
  }

  // One-sided upper bound (< high)
  if (high !== null && low === null) {
    const dMin = 0.0
    const dMax = Math.max(val * 1.25, high * 1.5)
    const total = dMax - dMin
    if (total <= 0) return null

    const pNorm = Math.max(10.0, (high / total) * 100)
    const pHigh = Math.max(5.0, 100.0 - pNorm)
    const pVal = Math.max(2.0, Math.min(97.0, (val / total) * 100))
    const markerColor = val > high ? '#f59e0b' : '#10b981'

    return (
      <div className="my-3 px-1">
        <div className="flex justify-between text-[11px] font-medium text-slate-500 mb-1.5">
          <span>0.0</span>
          <span className="text-emerald-700 font-semibold bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
            Desirable: &lt; {high} {unit}
          </span>
          <span>Max: {dMax.toFixed(1)}</span>
        </div>
        <div className="relative h-3 bg-slate-200 rounded-full flex overflow-visible">
          <div
            style={{ width: `${pNorm}%` }}
            className="bg-emerald-300 rounded-l-full"
            title={`Optimal range (< ${high})`}
          />
          <div
            style={{ width: `${pHigh}%` }}
            className="bg-rose-200 rounded-r-full"
            title={`High zone (> ${high})`}
          />
          <div
            style={{ left: `${pVal}%`, backgroundColor: markerColor }}
            className="absolute -top-1 w-1.5 h-5 rounded-full border-2 border-white shadow-md transform -translate-x-1/2 z-10 transition-all duration-300"
          />
        </div>
        <div className="relative h-4 mt-1">
          <span
            style={{ left: `${pVal}%`, color: markerColor }}
            className="absolute transform -translate-x-1/2 text-[11px] font-bold tracking-tight whitespace-nowrap"
          >
            ▲ {val} {unit}
          </span>
        </div>
      </div>
    )
  }

  return null
}
