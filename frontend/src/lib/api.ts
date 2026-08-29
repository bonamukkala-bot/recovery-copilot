export type RecoveryEvent = {
  id: string
  event_type: string
  payment_id: string | null
  order_id: string | null
  amount: number
  currency: string | null
  status: string | null
  error_code: string | null
  error_description: string | null
  method: string | null
  failure_type: string | null
  recovery_channel: string | null
  recovery_reason: string | null
  dispatch_status: string | null
  dispatch_message: string | null
  dispatched_at: string | null
  requires_approval: boolean
  approval_status: string
  outcome_status: string
  recovered_at: string | null
  created_at: string
}

const API_BASE = "http://127.0.0.1:8000"

export async function fetchEvents(): Promise<RecoveryEvent[]> {
  const res = await fetch(`${API_BASE}/events`)
  if (!res.ok) {
    throw new Error(`Failed to load events: ${res.status}`)
  }
  return res.json()
}
export type Metrics = {
  total_failures: number
  total_actioned: number
  total_recovered: number
  recovery_rate_percent: number
  contact_rate_percent: number
  avg_time_to_recovery_minutes: number | null
  cost_per_recovery_inr: number | null
  cost_basis: string
}

export async function fetchMetrics(): Promise<Metrics> {
  const response = await fetch(`${API_BASE}/metrics`)
  if (!response.ok) throw new Error('Failed to fetch metrics')
  return response.json()
}