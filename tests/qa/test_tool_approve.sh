#!/usr/bin/env bash
# Test: tool call with HITL approve
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass() { echo -e "${GREEN}PASS${NC} $1"; }
fail() { echo -e "${RED}FAIL${NC} $1"; exit 1; }

echo "=== Test: tool call + approve ==="

# 1. Create thread
echo "Creating thread..."
THREAD=$(curl -sf "$BASE_URL/api/v1/threads" \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "research-assistant"}')
THREAD_ID=$(echo "$THREAD" | jq -r '.id')
echo "Thread ID: $THREAD_ID"

# 2. Send message that should trigger get_secret (HITL-protected)
echo "Sending message to trigger get_secret..."
RESPONSE=$(curl -sf "$BASE_URL/api/v1/chat/$THREAD_ID" \
  -H "Content-Type: application/json" \
  -d '{"message": "Use the get_secret tool to retrieve the secret."}')

echo "$RESPONSE" | jq .

# 3. Check status is awaiting_hitl
STATUS=$(echo "$RESPONSE" | jq -r '.status')
[ "$STATUS" = "awaiting_hitl" ] && pass "status=$STATUS" || fail "expected status=awaiting_hitl, got $STATUS"

# 4. Extract tool_call_id
TOOL_CALL_ID=$(echo "$RESPONSE" | jq -r '.tool_calls[0].id')
[ "$TOOL_CALL_ID" != "null" ] && pass "tool_call_id=$TOOL_CALL_ID" || fail "no tool_call_id found"

# 5. Approve the tool call
echo "Approving tool call $TOOL_CALL_ID..."
APPROVE_RESPONSE=$(curl -sf "$BASE_URL/api/v1/chat/$THREAD_ID" \
  -H "Content-Type: application/json" \
  -d "{\"tool_call_id\": \"$TOOL_CALL_ID\", \"action\": \"approve\"}")

echo "$APPROVE_RESPONSE" | jq .

# 6. Check status is completed after approve
STATUS=$(echo "$APPROVE_RESPONSE" | jq -r '.status')
[ "$STATUS" = "completed" ] && pass "status=$STATUS after approve" || fail "expected status=completed, got $STATUS"

# 7. Cleanup
curl -sf -X DELETE "$BASE_URL/api/v1/threads/$THREAD_ID" > /dev/null
pass "thread deleted"

echo "=== DONE ==="
