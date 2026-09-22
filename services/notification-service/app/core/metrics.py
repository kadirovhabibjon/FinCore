from fincore_common import Counter

# spec Section 24: "DLT message count" — incremented wherever an event
# is actually dead-lettered (app/services/dispatch.py's `_dead_letter`),
# whether that's a permanent failure routed there immediately or a
# transient one that exhausted its retries.
DLT_MESSAGES_TOTAL = Counter(
    "fincore_dlt_messages_total", "Total events routed to the dead-letter topic."
)
