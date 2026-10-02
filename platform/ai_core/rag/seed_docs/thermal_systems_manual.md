# Thermal Systems Maintenance Manual (rev 4)

Thermal overheat on a rack or drive unit is declared when the measured temperature stays above 85 degrees Celsius for more than ten seconds. The first approved response is to throttle load on the affected node, reducing sustained load by between 10 and 90 percent depending on severity. Throttle load never exceeds 90 percent because a full stop must be handled as a shutdown.

If temperature exceeds 105 degrees Celsius or severity is critical, an emergency shutdown is required with a grace period of at most 60 seconds so dependent processes can drain. Emergency shutdown is a physical intervention and requires cryptographically signed human approval before execution.

After any thermal event the node must be scheduled for inspection within 72 hours to verify coolant flow and heat sink contact.
