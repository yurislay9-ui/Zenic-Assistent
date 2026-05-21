// ─── Zenic-Agents MCP Gateway — Redis Lua Scripts for Atomic Rate Limiting ──
// Lua scripts executed atomically inside Redis to prevent race conditions
// across multiple gateway instances.

/**
 * SLIDING_WINDOW_CHECK
 *
 * Atomic prune + count + conditional add for the sliding window algorithm.
 *
 * KEYS[1]  = the sorted set key (e.g. "zenic:rl:sw:{configKey}")
 * ARGV[1]  = window start timestamp (ms) — entries with score < this are pruned
 * ARGV[2]  = current timestamp (ms) — the new member's score
 * ARGV[3]  = unique request ID — the new member value
 * ARGV[4]  = max requests allowed in the window
 * ARGV[5]  = TTL for the key in milliseconds (windowMs + small buffer)
 *
 * Returns:
 *   {allowed (0|1), count_after, remaining, reset_at_ms}
 */
export const SLIDING_WINDOW_CHECK = `
local key        = KEYS[1]
local windowStart = tonumber(ARGV[1])
local now         = tonumber(ARGV[2])
local memberId    = ARGV[3]
local maxRequests = tonumber(ARGV[4])
local ttlMs       = tonumber(ARGV[5])

-- 1. Remove entries outside the sliding window
redis.call('ZREMRANGEBYSCORE', key, '-inf', windowStart)

-- 2. Count current entries in the window
local count = redis.call('ZCARD', key)

local allowed = 0
local remaining = 0

if count < maxRequests then
  -- 3a. Add the new request entry
  redis.call('ZADD', key, now, memberId)
  count = count + 1
  allowed = 1
  remaining = maxRequests - count
else
  -- 3b. Rate limited — do not add
  remaining = 0
end

-- 4. Set / refresh TTL so the key auto-expires when idle
redis.call('PEXPIRE', key, ttlMs)

-- 5. Calculate resetAt: earliest entry + windowMs
local earliest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local resetAt = now
if #earliest >= 2 then
  resetAt = tonumber(earliest[2])
end

return { allowed, count, remaining, resetAt }
`;

/**
 * FIXED_WINDOW_CHECK
 *
 * Atomic increment + conditional check + set TTL for the fixed window algorithm.
 *
 * KEYS[1]  = the counter key (e.g. "zenic:rl:fw:{configKey}:{windowIndex}")
 * ARGV[1]  = max requests allowed in the window
 * ARGV[2]  = TTL for the key in milliseconds (windowMs + small buffer)
 * ARGV[3]  = resetAt timestamp (ms) — (windowIndex + 1) * windowMs
 *
 * Returns:
 *   {allowed (0|1), count_after, remaining, reset_at_ms}
 */
export const FIXED_WINDOW_CHECK = `
local key        = KEYS[1]
local maxRequests = tonumber(ARGV[1])
local ttlMs       = tonumber(ARGV[2])
local resetAt     = tonumber(ARGV[3])

-- 1. Increment the counter
local count = redis.call('INCR', key)

-- 2. Set TTL only on first increment (count == 1)
if count == 1 then
  redis.call('PEXPIRE', key, ttlMs)
end

local allowed = 0
local remaining = 0

if count <= maxRequests then
  allowed = 1
  remaining = maxRequests - count
else
  remaining = 0
end

return { allowed, count, remaining, resetAt }
`;

/**
 * TOKEN_BUCKET_CHECK
 *
 * Atomic get + refill + conditional consume for the token bucket algorithm.
 *
 * KEYS[1]  = the hash key (e.g. "zenic:rl:tb:{configKey}")
 * ARGV[1]  = current timestamp (ms)
 * ARGV[2]  = max tokens (bucket capacity / burst size)
 * ARGV[3]  = refill rate per millisecond
 * ARGV[4]  = TTL for the key in milliseconds (windowMs * 2)
 *
 * Returns:
 *   {allowed (0|1), tokens_remaining, reset_at_ms, limit}
 */
export const TOKEN_BUCKET_CHECK = `
local key          = KEYS[1]
local now          = tonumber(ARGV[1])
local maxTokens    = tonumber(ARGV[2])
local refillPerMs  = tonumber(ARGV[3])
local ttlMs        = tonumber(ARGV[4])

-- 1. Read current bucket state
local data = redis.call('HMGET', key, 'tokens', 'lastRefill')

local tokens     = tonumber(data[1])
local lastRefill = tonumber(data[2])

-- 2. Initialize if not exists
if tokens == nil then
  tokens     = maxTokens
  lastRefill = now
end

-- 3. Refill tokens based on elapsed time
local elapsed = now - lastRefill
if elapsed > 0 then
  local tokensToAdd = elapsed * refillPerMs
  tokens = math.min(maxTokens, tokens + tokensToAdd)
  lastRefill = now
end

local allowed = 0
local consumed = 0

-- 4. Try to consume one token
if tokens >= 1 then
  tokens   = tokens - 1
  allowed  = 1
  consumed = 1
end

-- 5. Persist the updated state
redis.call('HMSET', key, 'tokens', tokens, 'lastRefill', lastRefill)
redis.call('PEXPIRE', key, ttlMs)

-- 6. Calculate resetAt
local resetAt = now
if tokens < maxTokens and refillPerMs > 0 then
  resetAt = now + math.ceil((maxTokens - tokens) / refillPerMs)
end

return { allowed, math.floor(tokens), resetAt, maxTokens }
`;
