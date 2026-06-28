# Design: Global Sequential Routing for Maximum Context Caching

## Overview
Currently, the API balances requests across multiple credentials (accounts/API keys) within the same priority group using weighted random selection (`random.choice` or `random.uniform`). This causes requests to "jump" between different accounts.

For providers like Google Gemini (Antigravity), Context Caching is tied to the **Google Cloud Project**.
- If multiple API keys belong to **different** projects, jumping between them means the cache is completely lost on every jump, leading to rapid quota exhaustion.
- If multiple API keys belong to the **same** project, they share the exact same rate limits (e.g., 15 RPM), so there is no benefit to having multiple keys in the first place, but if you do, jumping between them within the same project *would* theoretically share the cache. However, the standard use case is multiple projects to multiply rate limits.

To maximize caching, we will implement **Global Sequential Routing**.

## Design Changes

### 1. `app/routing/selector.py`
We will update `select_and_book` to remove randomness when selecting between credentials in the same priority group.
- **Sorting**: We will sort the `candidates` array by `str(c.id)`. Since UUIDs are static, this guarantees a deterministic and stable order for any given set of credentials.
- **Selection**: The router will simply iterate over the sorted candidates and try to book (`_try_book`). The first candidate that successfully books (i.e., has available concurrency and token quota) will be used.
- **Result**: The first credential in the sorted list will handle *all* requests until its limits are exhausted. Once exhausted, the system seamlessly moves to the second credential, and so on.

### 2. Ignoring `weight`
The `weight` column in the `Credential` model will effectively be ignored for load balancing, as the goal is to exhaust credentials sequentially rather than distribute load proportionally. (If needed in the future, weight could be used as a secondary sorting parameter, but sorting by `id` achieves the primary goal perfectly).

## Trade-offs
- **Pros**: Maximizes context caching (drastically reducing cost and token limit usage for repeated contexts). Extremely predictable behavior.
- **Cons**: Concentrates all load on a single account at a time, rather than distributing it evenly. This is actually desired in this context, but it means one account hits rate limits very quickly while others sit idle until needed.

## Next Steps
Proceed to implementation by updating `Selector.py`.
