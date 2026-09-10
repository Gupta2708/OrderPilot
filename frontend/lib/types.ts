export type RunStatus =
  | "PENDING"
  | "ACTING"
  | "SLEEPING"
  | "PAUSED"
  | "COMPLETED"
  | "TERMINATED";

export interface Supervisor {
  id: string;
  name: string;
  base_instruction: string;
  allowed_actions: string[];
  config: {
    wake_aggressiveness?: string;
    default_wake_minutes?: number;
    max_age_minutes?: number;
    require_approval_for?: string[];
    continue_as_new_after_events?: number;
  };
  created_at: string;
}

export interface RunSummary {
  id: string;
  order_id: string;
  supervisor_id: string;
  temporal_workflow_id: string;
  status: string;
  next_wake_at: string | null;
  last_wake_at: string | null;
  stats: Record<string, number>;
  created_at: string;
  completed_at: string | null;
}

export interface ActivityEntry {
  seq: number;
  type: string;
  source: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ProposedAction {
  tool: string;
  arguments: Record<string, unknown>;
}

export interface AgentDecision {
  decision: string;
  priority: string;
  reason_summary: string;
  actions: ProposedAction[];
  memory_update: string;
  sleep_minutes: number;
  completion_recommended: boolean;
  provider: string;
  trigger: string;
}

export interface WakeDecision {
  wake_now: boolean;
  severity: string;
  category: string;
  reason: string;
  rule: string;
  event_type?: string;
}

export interface FinalOutput {
  final_summary: string;
  important_actions: Record<string, unknown>[];
  learnings: string[];
  recommendations: string[];
  terminal_reason: string;
  stats: Record<string, number>;
}

export interface OrderState {
  payment?: { status?: string; reason?: string | null };
  fulfillment?: { status?: string };
  shipment?: { status?: string; tracking_id?: string | null; delay_reason?: string | null };
  delivery?: { status?: string };
  refund?: { status?: string; reason?: string | null };
  customer?: { last_message?: string | null };
}

export interface RunDetail extends RunSummary {
  order_state: OrderState;
  wake_guidance: string[];
  memory_summary: string;
  run_instructions: string[];
  latest_decision: AgentDecision | null;
  final_output: FinalOutput | null;
  timeline: ActivityEntry[];
}

export interface PendingApproval {
  approval_id: string;
  tool: string;
  arguments: Record<string, unknown>;
  requested_at: string | null;
}

export interface SupervisorTemplate {
  key: string;
  name: string;
  description: string;
  base_instruction: string;
  allowed_actions: string[];
  wake_aggressiveness: string;
  default_wake_minutes: number;
  max_age_minutes: number;
  require_approval_for: string[];
}

export interface RunAnalytics {
  run_id: string;
  order_id: string;
  status: string;
  events_received: number;
  agent_wakeups: number;
  no_wake_events: number;
  classifier_calls: number;
  scheduled_reviews: number;
  actions_executed: number;
  customer_actions: number;
  approvals_granted: number;
  approvals_denied: number;
  continuations: number;
  duration_seconds: number;
  wake_rate: number;
  actions_per_wake: number;
}

export interface RunState {
  run_id: string;
  order_id: string;
  source: "workflow" | "database";
  status: string;
  paused: boolean;
  terminal: boolean;
  terminal_reason: string | null;
  order_state: OrderState;
  memory_summary: string;
  run_instructions: string[];
  latest_decision: AgentDecision | null;
  latest_wake_decision: WakeDecision | null;
  executed_actions: Record<string, unknown>[];
  pending_approvals: PendingApproval[];
  wake_guidance: string[];
  next_wake_at: string | null;
  last_wake_at: string | null;
  pending_events: number;
  stats: Record<string, number>;
  final_output: FinalOutput | null;
}
