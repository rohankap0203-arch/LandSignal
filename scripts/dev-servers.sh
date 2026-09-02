#!/usr/bin/env bash
# Compatibility wrapper — always use the Cloud Agent supervisor.
exec bash "$(cd "$(dirname "$0")" && pwd)/cloud-agent-start.sh"
