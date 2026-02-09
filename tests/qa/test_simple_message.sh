#!/usr/bin/env bash
# Test: simple message without tool usage
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass() { echo -e "${GREEN}PASS${NC} $1"; }
fail() { echo -e "${RED}FAIL${NC} $1"; exit 1; }

echo "=== Test: simple message (no tool) ==="

# 1. Create thread
echo "Creating thread..."
THREAD=$(curl -sf "$BASE_URL/api/v1/threads" \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "research-assistant"}')
THREAD_ID=$(echo "$THREAD" | jq -r '.id')
echo "Thread ID: $THREAD_ID"

# 2. Send a simple message that should NOT trigger any tool
echo "Sending message..."
RESPONSE=$(curl -sf "$BASE_URL/api/v1/chat/$THREAD_ID" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is hexagonal architecture? Answer in one sentence."}')

echo "$RESPONSE" | jq .

# 3. Check status is completed
STATUS=$(echo "$RESPONSE" | jq -r '.status')
[ "$STATUS" = "completed" ] && pass "status=$STATUS" || fail "expected status=completed, got $STATUS"

# 4. Check no tool_calls
TOOL_CALLS=$(echo "$RESPONSE" | jq '.tool_calls')
[ "$TOOL_CALLS" = "null" ] && pass "no tool_calls" || fail "unexpected tool_calls: $TOOL_CALLS"

# 5. Cleanup
curl -sf -X DELETE "$BASE_URL/api/v1/threads/$THREAD_ID" > /dev/null
pass "thread deleted"

echo "=== DONE ==="
