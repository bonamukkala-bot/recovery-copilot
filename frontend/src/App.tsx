import { useEffect, useState, useCallback } from 'react'
import { fetchEvents, fetchMetrics, type RecoveryEvent, type Metrics } from './lib/api'

const CHANNEL_STYLES: Record<string, { label: string; border: string; chip: string }> = {
  sms: { label: 'SMS', border: 'border-l-blue-400', chip: 'bg-blue-400/10 text-blue-300' },
  whatsapp: { label: 'WhatsApp', border: 'border-l-emerald-400', chip: 'bg-emerald-400/10 text-emerald-300' },
  voice_call: { label: 'Voice Call', border: 'border-l-amber-400', chip: 'bg-amber-400/10 text-amber-300' },
  auto_retry: { label: 'Auto-Retry', border: 'border-l-teal-400', chip: 'bg-teal-400/10 text-teal-300' },
  none: { label: 'Flagged', border: 'border-l-slate-500', chip: 'bg-slate-500/10 text-slate-400' },
}

function channelStyle(channel: string | null) {
  return CHANNEL_STYLES[channel ?? 'none'] ?? CHANNEL_STYLES.none
}

function formatRupees(paise: number) {
  return (paise / 100).toLocaleString('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

function App() {
  const [events, setEvents] = useState<RecoveryEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [eventsData, metricsData] = await Promise.all([fetchEvents(), fetchMetrics()])
      setEvents(eventsData)
      setMetrics(metricsData)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, 15000)
    return () => clearInterval(interval)
  }, [load])

  const totalEvents = events.length
  const classified = events.filter((e) => e.failure_type).length
  const actioned = events.filter((e) => e.recovery_channel && e.recovery_channel !== 'none').length

  return (
    <div className="min-h-screen px-6 py-10 md:px-12">
      <header className="mb-10 flex items-baseline justify-between border-b border-white/10 pb-6">
        <div>
          <p className="font-mono-tab text-xs uppercase tracking-[0.2em] text-[#8B93A7]">Razorpay Buildathon · Track 3</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight md:text-3xl">Recovery Copilot</h1>
        </div>
        <button
          onClick={load}
          className="rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-[#E8ECF4] transition hover:bg-white/10"
        >
          Refresh
        </button>
      </header>

      <section className="mb-10 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatTile label="Events Ingested" value={totalEvents} />
        <StatTile label="Classified" value={classified} accent="#2DD4BF" />
        <StatTile label="Recovery Actions Fired" value={actioned} accent="#F2B705" />
      </section>

      {metrics && (
        <section className="mb-10 grid grid-cols-1 gap-4 sm:grid-cols-4">
          <StatTile label="Recovery Rate" value={`${metrics.recovery_rate_percent}%`} accent="#2DD4BF" />
          <StatTile label="Contact Rate" value={`${metrics.contact_rate_percent}%`} accent="#F2B705" />
          <StatTile
            label="Avg Time to Recovery"
            value={metrics.avg_time_to_recovery_minutes !== null ? `${metrics.avg_time_to_recovery_minutes}m` : '—'}
          />
          <StatTile
            label="Cost / Recovery"
            value={metrics.cost_per_recovery_inr !== null ? `₹${metrics.cost_per_recovery_inr}` : '—'}
          />
        </section>
      )}

      <section>
        <h2 className="mb-4 font-mono-tab text-xs uppercase tracking-[0.2em] text-[#8B93A7]">Event Ledger</h2>

        {loading && <p className="text-sm text-[#8B93A7]">Loading events…</p>}
        {error && <p className="text-sm text-[#EF6461]">Couldn't reach the backend — is uvicorn running? ({error})</p>}
        {!loading && !error && events.length === 0 && (
          <p className="text-sm text-[#8B93A7]">No events yet. Send a test webhook to see it appear here.</p>
        )}

        <div className="flex flex-col gap-2">
          {events.map((event) => {
  const style = channelStyle(event.recovery_channel)
  const isExpanded = expandedId === event.id
  return (
    <div key={event.id}>
      <div
        onClick={() => setExpandedId(isExpanded ? null : event.id)}
        className={`flex cursor-pointer flex-col gap-2 rounded-md border-l-4 bg-[#131B2E] px-4 py-3 ${style.border} sm:flex-row sm:items-center sm:justify-between transition hover:bg-[#17203A]`}
      >
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-mono-tab text-sm text-[#E8ECF4]">{event.payment_id}</span>
            <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${style.chip}`}>
              {style.label}
            </span>
            {event.approval_status === 'pending' && (
              <span className="rounded bg-orange-400/10 px-1.5 py-0.5 text-[11px] font-medium text-orange-300">
                Pending Approval
              </span>
            )}
            {event.outcome_status === 'recovered' && (
              <span className="rounded bg-teal-400/10 px-1.5 py-0.5 text-[11px] font-medium text-teal-300">
                Recovered
              </span>
            )}
          </div>
          <p className="mt-1 truncate text-sm text-[#8B93A7]">
            {event.failure_type ?? 'unclassified'} · {event.recovery_reason ?? 'awaiting classification'}
          </p>
          {event.dispatch_message && (
            <p className="mt-1 truncate text-xs text-[#5C6478]">
              → {event.dispatch_message}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-4 font-mono-tab text-sm">
          <span className="text-[#E8ECF4]">{formatRupees(event.amount)}</span>
          <span className="text-[#8B93A7]">{formatTime(event.created_at)}</span>
        </div>
      </div>

      {isExpanded && (
        <div className="rounded-b-md border-l-4 border-white/5 bg-[#0F1626] px-4 py-4 text-sm">
          <div className="grid grid-cols-1 gap-x-8 gap-y-2 sm:grid-cols-2">
            <DetailRow label="Order ID" value={event.order_id ?? '—'} />
            <DetailRow label="Event Type" value={event.event_type} />
            <DetailRow label="Method" value={event.method ?? '—'} />
            <DetailRow label="Error Code" value={event.error_code ?? '—'} />
            <DetailRow label="Error Description" value={event.error_description ?? '—'} />
            <DetailRow label="Failure Type" value={event.failure_type ?? 'unclassified'} />
            <DetailRow label="Recovery Channel" value={event.recovery_channel ?? '—'} />
            <DetailRow label="Recovery Reason" value={event.recovery_reason ?? '—'} />
            <DetailRow label="Requires Approval" value={event.requires_approval ? 'Yes' : 'No'} />
            <DetailRow label="Approval Status" value={event.approval_status} />
            <DetailRow label="Dispatch Status" value={event.dispatch_status ?? '—'} />
            <DetailRow label="Dispatched At" value={event.dispatched_at ? formatTime(event.dispatched_at) : '—'} />
            <DetailRow label="Outcome Status" value={event.outcome_status} />
            <DetailRow label="Recovered At" value={event.recovered_at ? formatTime(event.recovered_at) : '—'} />
          </div>
          {event.dispatch_message && (
            <div className="mt-3 border-t border-white/5 pt-3">
              <p className="text-xs uppercase tracking-wide text-[#5C6478]">Message Sent</p>
              <p className="mt-1 font-mono-tab text-xs text-[#8B93A7]">{event.dispatch_message}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
})}
        </div>
      </section>
    </div>
  )
}

function StatTile({ label, value, accent }: { label: string; value: number | string; accent?: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-[#131B2E] px-5 py-4">
      <p className="font-mono-tab text-xs uppercase tracking-[0.15em] text-[#8B93A7]">{label}</p>
      <p className="mt-1 font-mono-tab text-3xl font-semibold" style={{ color: accent ?? '#E8ECF4' }}>
        {value}
      </p>
    </div>
  )
}
function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-[#5C6478]">{label}</p>
      <p className="mt-0.5 font-mono-tab text-[#C9CEDA]">{value}</p>
    </div>
  )
}
export default App