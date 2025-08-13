# Discovery Mode Changes to scanner.py

## Important Note
The changes made to scanner.py for Discovery Mode testing should NOT be merged to the main branch as they will break the diagnosis mode. 

## Changes Made (DO NOT MERGE):

### 1. Async Playwright Conversion
- Changed from sync to async Playwright functions
- This breaks ThreadPoolExecutor compatibility in diagnosis mode
- Files affected: scanner.py lines 66, 103-127, 921-1084

### 2. Screenshot Capture Optimizations
- Reduced timeouts from 45s to 30s
- Less aggressive scrolling (25 scrolls instead of 75)
- Added 90-second timeout per screenshot
- Files affected: scanner.py lines 1873-1927, 2674-2727

### 3. Discovery Mode Integration
- Added Discovery analysis functions
- Added init_discovery_mode()
- Files affected: scanner.py lines 2832-2951

## Safe Changes (CAN BE MERGED):

### 1. UTF-8 Encoding Fix
- Added safe_encode_utf8() function
- Improved text encoding handling
- Files affected: scanner.py lines 1048-1084

### 2. Thread-safe timeout fixes
- Replaced signal-based timeouts with concurrent.futures
- Files affected: scanner.py lines 2429-2478, 2538-2559

## Recommended Approach:

For production deployment, keep Discovery Mode changes in a separate branch and:
1. Only merge the safe changes (UTF-8 fixes, thread-safe timeouts)
2. Keep async Playwright changes isolated to Discovery Mode branch
3. Consider maintaining two versions of scanner.py or use feature flags

## To Revert Breaking Changes:

```bash
# To revert only the async changes while keeping Discovery Mode:
git checkout main -- scanner.py
# Then manually re-apply only the Discovery Mode specific changes
```