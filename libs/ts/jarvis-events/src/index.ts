// Public surface of @jarvis/events: generated zod schemas + helpers.
export * from "./generated/index.js";

import { EventEnvelopeSchema, type EventEnvelope, SUBJECT_SCHEMAS } from "./generated/index.js";

/**
 * Validate a raw WebSocket/NATS message into a typed envelope.
 * Returns null for messages that aren't valid envelopes (forward compatibility:
 * unknown subjects still parse — only the payload stays untyped).
 */
export function parseEnvelope(raw: unknown): EventEnvelope | null {
  const result = EventEnvelopeSchema.safeParse(raw);
  return result.success ? result.data : null;
}

/** Parse an envelope's payload with its subject schema; null if subject unknown. */
export function parsePayload(envelope: EventEnvelope): unknown | null {
  const schema = SUBJECT_SCHEMAS[envelope.type as keyof typeof SUBJECT_SCHEMAS];
  if (!schema) return null;
  const result = schema.safeParse(envelope.data);
  return result.success ? result.data : null;
}
