import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { useTelemetry } from '../hooks/useTelemetry'

interface Props {
  assetId: string
  tagName: string
  minutes?: number
  height?: number
  color?: string
}

const TAG_META: Record<string, { unit: string; decimals: number }> = {
  Temperature_degC: { unit: '°C',    decimals: 1 },
  Pressure_bar:     { unit: 'bar',   decimals: 2 },
  Vibration_mm_s:   { unit: 'mm/s',  decimals: 2 },
  FlowRate_Lmin:    { unit: 'L/min', decimals: 1 },
  Current_A:        { unit: 'A',     decimals: 2 },
  Speed_rpm:        { unit: 'rpm',   decimals: 0 },
  Speed_mps:        { unit: 'm/s',   decimals: 2 },
  Level_pct:        { unit: '%',     decimals: 1 },
  FillRate_Lmin:    { unit: 'L/min', decimals: 1 },
}

export function TagSparkline({ assetId, tagName, minutes = 60, height = 100, color = '#f59e0b' }: Props) {
  const { data, isLoading, isError } = useTelemetry(assetId, tagName, minutes)
  const meta = TAG_META[tagName] ?? { unit: '', decimals: 2 }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center" style={{ height }}>
        <div className="text-xs text-slate-600">Loading…</div>
      </div>
    )
  }

  if (isError || !data || data.readings.length === 0) {
    return (
      <div className="flex items-center justify-center" style={{ height }}>
        <div className="text-xs text-slate-600">No data</div>
      </div>
    )
  }

  const chartData = data.readings.map((r) => ({
    t: new Date(r.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    v: r.value,
    q: r.opc_quality_label,
  }))

  const values = data.readings.map((r) => r.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const pad = (max - min) * 0.12 || 0.5
  const domain: [number, number] = [min - pad, max + pad]

  const fmt = (v: number) =>
    meta.decimals === 0 ? Math.round(v).toString() : v.toFixed(meta.decimals)

  const yTickFormatter = (v: number) =>
    meta.unit ? `${fmt(v)} ${meta.unit}` : fmt(v)

  const yWidth = meta.unit ? 52 : 36

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 4 }}>
        <XAxis
          dataKey="t"
          tick={{ fontSize: 9, fill: '#475569' }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          domain={domain}
          tick={{ fontSize: 9, fill: '#475569' }}
          tickLine={false}
          axisLine={false}
          width={yWidth}
          tickFormatter={yTickFormatter}
          tickCount={4}
        />
        <Tooltip
          contentStyle={{
            background: '#0f172a',
            border: '1px solid #1e293b',
            borderRadius: 4,
            fontSize: 11,
            color: '#cbd5e1',
          }}
          itemStyle={{ color: color }}
          formatter={(v: number) => [`${fmt(v)}${meta.unit ? ' ' + meta.unit : ''}`, tagName]}
          labelStyle={{ color: '#64748b' }}
        />
        <Line
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          activeDot={{ r: 3, fill: color }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
