class Topics:
    TELEMETRY = "telemetry.raw"
    ANOMALIES = "anomalies.detected"
    SWARM_EVENTS = "swarm.events"
    APPROVAL_REQUESTS = "approvals.requests"
    APPROVAL_DECISIONS = "approvals.decisions"
    REMEDIATION = "remediation.executed"
    FL_UPDATES = "fl.updates"
    FL_GLOBAL = "fl.global"

    ALL = (TELEMETRY, ANOMALIES, SWARM_EVENTS, APPROVAL_REQUESTS, APPROVAL_DECISIONS, REMEDIATION, FL_UPDATES, FL_GLOBAL)
    UI_STREAM = (TELEMETRY, ANOMALIES, SWARM_EVENTS, APPROVAL_REQUESTS, REMEDIATION, FL_GLOBAL)
