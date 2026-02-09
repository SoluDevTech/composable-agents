#!/usr/bin/env bash
# Test: full conversation exercising both tools with approve and reject
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

pass() { echo -e "${GREEN}PASS${NC} $1"; }
fail() { echo -e "${RED}FAIL${NC} $1"; exit 1; }
step() { echo -e "\n${BLUE}--- $1 ---${NC}"; }

echo "=== Test: full conversation (both tools, approve + reject) ==="

# 1. Create thread
step "1. Create thread"
THREAD=$(curl -sf "$BASE_URL/api/v1/threads" \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "research-assistant"}')
THREAD_ID=$(echo "$THREAD" | jq -r '.id')
echo "Thread ID: $THREAD_ID"

# 2. Call get_user_name → approve
step "2. get_user_name + approve"
RESPONSE=$(curl -sf "$BASE_URL/api/v1/chat/$THREAD_ID" \
  -H "Content-Type: application/json" \
  -d '{"message": "Use the get_user_name tool to tell me the user name."}')
echo "$RESPONSE" | jq .
STATUS=$(echo "$RESPONSE" | jq -r '.status')
[ "$STATUS" = "awaiting_hitl" ] && pass "get_user_name awaiting_hitl" || fail "expected awaiting_hitl, got $STATUS"

TOOL_CALL_ID=$(echo "$RESPONSE" | jq -r '.tool_calls[0].id')
[ "$TOOL_CALL_ID" != "null" ] && pass "tool_call_id=$TOOL_CALL_ID" || fail "no tool_call_id"

echo "Approving..."
RESPONSE=$(curl -sf "$BASE_URL/api/v1/chat/$THREAD_ID" \
  -H "Content-Type: application/json" \
  -d "{\"tool_call_id\": \"$TOOL_CALL_ID\", \"action\": \"approve\"}")
echo "$RESPONSE" | jq .
STATUS=$(echo "$RESPONSE" | jq -r '.status')
[ "$STATUS" = "completed" ] && pass "approved → completed" || fail "expected completed, got $STATUS"

# 3. Call get_user_name → reject
step "3. get_user_name + reject"
RESPONSE=$(curl -sf "$BASE_URL/api/v1/chat/$THREAD_ID" \
  -H "Content-Type: application/json" \
  -d '{"message": "Use the get_user_name tool again please."}')
echo "$RESPONSE" | jq .
STATUS=$(echo "$RESPONSE" | jq -r '.status')
[ "$STATUS" = "awaiting_hitl" ] && pass "get_user_name awaiting_hitl" || fail "expected awaiting_hitl, got $STATUS"

TOOL_CALL_ID=$(echo "$RESPONSE" | jq -r '.tool_calls[0].id')
[ "$TOOL_CALL_ID" != "null" ] && pass "tool_call_id=$TOOL_CALL_ID" || fail "no tool_call_id"

echo "Rejecting..."
RESPONSE=$(curl -sf "$BASE_URL/api/v1/chat/$THREAD_ID" \
  -H "Content-Type: application/json" \
  -d "{\"tool_call_id\": \"$TOOL_CALL_ID\", \"action\": \"reject\", \"reason\": \"not needed\"}")
echo "$RESPONSE" | jq .
STATUS=$(echo "$RESPONSE" | jq -r '.status')
[ "$STATUS" = "completed" ] && pass "rejected → completed" || fail "expected completed, got $STATUS"

# 4. Call get_secret → approve
step "4. get_secret + approve"
RESPONSE=$(curl -sf "$BASE_URL/api/v1/chat/$THREAD_ID" \
  -H "Content-Type: application/json" \
  -d '{"message": "Use the get_secret tool to retrieve the secret."}')
echo "$RESPONSE" | jq .
STATUS=$(echo "$RESPONSE" | jq -r '.status')
[ "$STATUS" = "awaiting_hitl" ] && pass "get_secret awaiting_hitl" || fail "expected awaiting_hitl, got $STATUS"

TOOL_CALL_ID=$(echo "$RESPONSE" | jq -r '.tool_calls[0].id')
[ "$TOOL_CALL_ID" != "null" ] && pass "tool_call_id=$TOOL_CALL_ID" || fail "no tool_call_id"

echo "Approving..."
RESPONSE=$(curl -sf "$BASE_URL/api/v1/chat/$THREAD_ID" \
  -H "Content-Type: application/json" \
  -d "{\"tool_call_id\": \"$TOOL_CALL_ID\", \"action\": \"approve\"}")
echo "$RESPONSE" | jq .
STATUS=$(echo "$RESPONSE" | jq -r '.status')
[ "$STATUS" = "completed" ] && pass "approved → completed" || fail "expected completed, got $STATUS"

# 5. Call get_secret → reject
step "5. get_secret + reject"
RESPONSE=$(curl -sf "$BASE_URL/api/v1/chat/$THREAD_ID" \
  -H "Content-Type: application/json" \
  -d '{"message": "Use the get_secret tool again please."}')
echo "$RESPONSE" | jq .
STATUS=$(echo "$RESPONSE" | jq -r '.status')
[ "$STATUS" = "awaiting_hitl" ] && pass "get_secret awaiting_hitl" || fail "expected awaiting_hitl, got $STATUS"

TOOL_CALL_ID=$(echo "$RESPONSE" | jq -r '.tool_calls[0].id')
[ "$TOOL_CALL_ID" != "null" ] && pass "tool_call_id=$TOOL_CALL_ID" || fail "no tool_call_id"

echo "Rejecting..."
RESPONSE=$(curl -sf "$BASE_URL/api/v1/chat/$THREAD_ID" \
  -H "Content-Type: application/json" \
  -d "{\"tool_call_id\": \"$TOOL_CALL_ID\", \"action\": \"reject\", \"reason\": \"not authorized\"}")
echo "$RESPONSE" | jq .
STATUS=$(echo "$RESPONSE" | jq -r '.status')
[ "$STATUS" = "completed" ] && pass "rejected → completed" || fail "expected completed, got $STATUS"

# 6. Cleanup
step "6. Cleanup"
curl -sf -X DELETE "$BASE_URL/api/v1/threads/$THREAD_ID" > /dev/null
pass "thread deleted"

echo -e "\n=== DONE ==="
