# Cache Layer Architecture

This document describes the cache layer in our system. The cache sits
between the application server and the primary database, absorbing
read load and providing a hot path for repeated queries.

## Cache layer

The cache layer is an in-memory key-value store that fronts the
primary database. It holds the most recently read rows and serves
them on subsequent reads. The store uses a least-recently-used
eviction policy with a 1 GB memory budget.

### Read path

On a read, the application first asks the cache. On a hit, the
cached row is returned in under 1 ms. On a miss, the application
falls through to the database, writes the result back into the
cache, and returns the row to the client.

### Write path

On a write, the application updates the database first, then
invalidates the matching cache entry. We chose invalidate-over-write
because it keeps the cache simple and avoids race conditions between
concurrent writers.

### Eviction

The cache evicts the least-recently-used entry when the memory
budget is exceeded. The eviction happens on a background goroutine
so the read path never blocks.

### Failure modes

If the cache is unreachable, the application falls through to the
database. The cache is treated as a pure performance optimization;
correctness is preserved even when the cache is entirely down.

## Cache stampede

When a popular key expires, every concurrent reader misses the
cache and hits the database at the same time. We prevent the
stampede with single-flight: only the first reader queries the
database, the rest wait for its result.

## Related systems

The cache layer is the front for a read-replica Postgres cluster
that lives behind the primary. The replicas lag the primary by
around 200 ms, so the cache absorbs the lag and shields the
application from it.
