# ADR-0004: Message Broker Choice — Kafka

## Status

Accepted

## Context

FinCore needs a message broker for the asynchronous side of the system
(ADR-0003): delivering domain events from producers
(`identity-service`, `ledger-service`, `payment-service`, `fraud-service`)
to multiple independent consumers (`notification-service`,
`webhook-service`, `audit-service`, and `payment-service` itself when
reacting to `ledger.posting.completed`).

The requirements that matter for this choice:

1. **Multiple independent consumer groups per event.** A single
   `payment.completed` event must reach `notification-service`,
   `webhook-service`, and `audit-service` — each independently, each
   tracking its own read position, with one consumer's failure or lag
   never affecting another's.
2. **Durable retention and replay.** `audit-service` is the system's record
   of what happened; if it is down for a while or a new consumer needs to
   be backfilled, events must still be there to read later, not only
   delivered once to whoever happened to be listening.
3. **Per-aggregate ordering.** Events for the same aggregate (e.g. the same
   transfer) must be processed in the order they were produced, without
   requiring global ordering across all aggregates.
4. **At-least-once delivery is acceptable and expected** — every consumer
   in FinCore is already required to be idempotent (ADR-0003, `processed_events`
   table), so the broker does not need to guarantee exactly-once.

## Decision

Use **Kafka**.

* Each domain event type is published to a topic (or a small number of
  topics grouped by aggregate type), keyed by `aggregate_id` as the
  partition key. This gives per-aggregate ordering (all events for one
  transfer land on the same partition, in order) without requiring a
  single global order.
* Each downstream service runs its own **consumer group**
  (`notification-service`, `webhook-service`, `audit-service`, and
  `payment-service`'s ledger-event consumer), so every group independently
  receives every event and tracks its own offset. One group's lag or
  outage never blocks another.
* Kafka's log-based retention means a new consumer (or one recovering from
  an outage) can read from the beginning of its assigned partitions rather
  than losing events that were published while it was down — this is what
  makes `audit-service` a trustworthy record and makes replay possible for
  debugging or backfilling.
* Delivery is at-least-once by construction (a message can be re-delivered
  after a consumer restart before committing its offset). This is
  acceptable *because* ADR-0003 already requires every consumer to be
  idempotent via a `processed_events(event_id PRIMARY KEY)` table written
  in the same transaction as the side effect — the broker's delivery
  guarantee and the consumer's idempotency guarantee together give the
  system effectively-once processing without needing the broker to
  provide it.
* Consumers that exhaust their retry budget for an event route it to a
  **dead-letter topic** for manual inspection/replay (Section 16 of the
  spec), rather than blocking their partition indefinitely.

## Consequences

* Kafka is operationally heavier than a simple queue: it requires
  ZooKeeper or KRaft, careful partition/topic planning, and consumer group
  monitoring (consumer lag becomes a first-class metric — Section 24 of
  the spec already lists "Kafka consumer lag" and "DLT message count").
  This cost is accepted because the durability and replay requirement
  (point 2 above) is a hard requirement for `audit-service`, not a nice
  to have.
* Producers must implement the transactional outbox pattern (a producer
  cannot simply "publish to Kafka" inline — see the outbox rationale in
  `glossary.md`); this is required regardless of broker choice, but Kafka
  does not remove the need for it.
* Every consumer must be written idempotently from day one — there is no
  "exactly-once, so we can skip this" shortcut available.
* Local development needs a Kafka container (plus, optionally, `kafka-ui`
  for inspecting topics), added in Phase 4 per the roadmap — not before,
  per Section 25's "do not create unnecessary infrastructure before the
  application needs it."

## Alternatives Considered

* **RabbitMQ** — a strong choice for task-queue-style, work-distribution
  messaging (competing consumers dividing up a queue), and operationally
  simpler to run than Kafka. Rejected for FinCore's event backbone because:
  - RabbitMQ's model is fundamentally about *queues* being drained;
    getting the same message to multiple independent consumer groups
    requires fanning out via exchanges to per-consumer queues, which works
    but does not give the same natural, built-in "replay from any point in
    a durable log" story that `audit-service` needs.
  - Long-term retention of already-consumed messages is not RabbitMQ's
    design center (classic queues discard on ack; streams narrow this gap
    but were not mature/standard enough to justify picking RabbitMQ
    *because* of them over Kafka's log model, which has this built in from
    the start).
  - RabbitMQ remains a reasonable choice for a future *task queue* use case
    (e.g. background job dispatch) if one arises that doesn't need
    replay — but that is a different problem from the domain-event
    backbone this ADR is about, and is not introduced speculatively
    (Section 4: "do not introduce technology unless there is a real
    reason").
* **No broker — direct HTTP fan-out from producers to each consumer** —
  rejected outright: it would make every producer's request synchronously
  (or manually-asynchronously, badly) depend on every consumer's
  availability, directly violating the sync/async separation in ADR-0003
  and losing durability entirely (an event to a down consumer would simply
  be lost).
