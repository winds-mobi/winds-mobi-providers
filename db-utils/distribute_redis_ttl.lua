local cursor = "0"
local keys_scanned = 0
local keys_expire_today = 0
local keys_expire_this_month = 0;
local keys_error_limit = 0
local keys_error = 0
local keys_updated = 0
local keys_persistent_skipped = 0
local keys_not_found = 0

repeat
    local scan_result = redis.call("SCAN", cursor, "MATCH", "*", "COUNT", "250") -- Adjust COUNT as needed, 250-1000 is usually fine
    cursor = scan_result[1]
    local keys = scan_result[2]

    for i, key in ipairs(keys) do
        keys_scanned = keys_scanned + 1
        local current_ttl = redis.call("TTL", key)

        if current_ttl < 24 * 3600 then
            keys_expire_today = keys_expire_today + 1
        elseif current_ttl < 30 * 24 * 3600 then
            keys_expire_this_month = keys_expire_this_month + 1
        end

        if current_ttl > 0 then
            -- Key exists and has a TTL, update it
            local error = redis.call("HGET", key, "error")
            if error then
                if string.find(error, "UsageLimitException") then
                    -- redis.call("EXPIRE", key, math.random(1, 3600))
                    keys_error_limit = keys_error_limit + 1
                else
                    redis.log(redis.LOG_NOTICE, "Error with key=" .. key .. ", error=" .. error)
                    -- redis.call("EXPIRE", key, math.random(1, 30 * 24 * 3600))
                    keys_error = keys_error + 1
                end
            else
                -- redis.call("EXPIRE", key, math.random(1, 365 * 24 * 3600))
                keys_updated = keys_updated + 1
            end
        elseif current_ttl == -1 then
            -- Key exists but is persistent (no TTL), skip it
            keys_persistent_skipped = keys_persistent_skipped + 1
        else
            -- Key does not exist (current_ttl == -2) or other issue
            keys_not_found = keys_not_found + 1
        end
    end
until cursor == "0"

local summary = "Update Summary: Keys Scanned: " .. keys_scanned ..
        ", Will expire today: " .. keys_expire_today ..
        ", Will expire this month: " .. keys_expire_this_month ..
        ", Usage Limit: " .. keys_error_limit ..
        ", Error: " .. keys_error ..
        ", Updated: " .. keys_updated ..
        ", Persistent (Skipped): " .. keys_persistent_skipped ..
        ", Not Found (Skipped): " .. keys_not_found

redis.log(redis.LOG_NOTICE, summary)
return summary
