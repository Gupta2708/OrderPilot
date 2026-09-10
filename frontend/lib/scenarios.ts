export interface ScenarioStep {
  type: string;
  label: string;
  payload?: Record<string, unknown>;
}

export interface Scenario {
  id: string;
  name: string;
  description: string;
  steps: ScenarioStep[];
}

/** The four assignment scenarios, driven one step at a time. */
export const SCENARIOS: Scenario[] = [
  {
    id: "happy-path",
    name: "Happy Path",
    description: "Nothing goes wrong; most events never wake the agent.",
    steps: [
      { type: "order_created", label: "Order created" },
      { type: "payment_confirmed", label: "Payment confirmed" },
      { type: "shipment_created", label: "Shipment created", payload: { tracking_id: "TRK-1001" } },
      { type: "delivered", label: "Delivered" },
    ],
  },
  {
    id: "payment-trouble",
    name: "Payment Trouble",
    description: "A failed payment wakes the agent, then recovers.",
    steps: [
      { type: "order_created", label: "Order created" },
      { type: "payment_failed", label: "Payment failed", payload: { reason: "card_declined" } },
      { type: "payment_confirmed", label: "Payment confirmed" },
      { type: "shipment_created", label: "Shipment created", payload: { tracking_id: "TRK-1002" } },
      { type: "delivered", label: "Delivered" },
    ],
  },
  {
    id: "delivery-crisis",
    name: "Delivery Crisis",
    description: "A delay plus an anxious customer drives escalation.",
    steps: [
      { type: "order_created", label: "Order created" },
      { type: "payment_confirmed", label: "Payment confirmed" },
      { type: "shipment_created", label: "Shipment created", payload: { tracking_id: "TRK-1003" } },
      { type: "shipment_delayed", label: "Shipment delayed", payload: { reason: "storm" } },
      {
        type: "customer_message_received",
        label: "Customer message",
        payload: { message: "Where is my order? I need it tomorrow." },
      },
      { type: "delivered", label: "Delivered" },
    ],
  },
  {
    id: "refund-risk",
    name: "Refund Risk",
    description: "The customer escalates toward a refund.",
    steps: [
      { type: "order_created", label: "Order created" },
      { type: "payment_confirmed", label: "Payment confirmed" },
      { type: "shipment_created", label: "Shipment created", payload: { tracking_id: "TRK-1004" } },
      {
        type: "customer_message_received",
        label: "Customer message",
        payload: { message: "This is taking far too long, I want to cancel." },
      },
      { type: "refund_requested", label: "Refund requested", payload: { reason: "late_delivery" } },
    ],
  },
];

/** Every event type the injector offers, including one the system will not recognise. */
export const EVENT_TYPES = [
  "order_created",
  "payment_confirmed",
  "payment_failed",
  "shipment_created",
  "shipment_delayed",
  "delivered",
  "refund_requested",
  "refund_completed",
  "order_cancelled",
  "customer_message_received",
  "warehouse_fire",
];
