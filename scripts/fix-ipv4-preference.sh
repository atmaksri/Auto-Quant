#!/usr/bin/env bash
# Force IPv4 preference system-wide (fixes freqtrade bot hanging on dead IPv6 route)
# Review: this adds one precedence line to /etc/gai.conf that makes getaddrinfo()
# return IPv4 addresses first for dual-stack hosts. Safe, reversible, standard
# fix for networks with broken IPv6. No services need restarting except the bot.
set -euo pipefail

CONF=/etc/gai.conf
RULE="precedence ::ffff:0:0/96  100"

if grep -q "^precedence ::ffff:0:0/96" "$CONF"; then
    echo "IPv4 precedence rule already present in $CONF — nothing to do."
else
    echo "# Force IPv4 preference for dual-stack lookups (added $(date -Iseconds))" >> "$CONF"
    echo "$RULE" >> "$CONF"
    echo "Added to $CONF: $RULE"
fi

echo "--- verifying with a dual-stack lookup ---"
getent ahosts api.kraken.com | head -4
echo "--- (first line should now be an IPv4 104.x address) ---"

echo ""
echo "Now restart the paper bot as the user (no sudo needed):"
echo "  systemctl --user restart eth1-paper.service"
