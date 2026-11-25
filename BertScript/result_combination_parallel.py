"""Stage 3 chunk mapping and process-pool lifecycle, without data dependencies."""


def parallelize_chunks(data, func, num_of_processes, *, split, pool_factory,
                       concatenate):
    """Preserve ordered mapping and concatenation; always reap failed pools.

    Split before acquiring resources, as in the legacy caller. On failure
    preserve the primary exception even if best-effort cleanup also fails.
    """
    chunks = split(data, num_of_processes)
    pool = pool_factory(num_of_processes)
    try:
        result = concatenate(pool.map(func, chunks))
        pool.close()
        pool.join()
    except BaseException:
        # KeyboardInterrupt also requires cleanup; never retry the work.
        try:
            pool.terminate()
        except BaseException:
            pass
        try:
            pool.join()
        except BaseException:
            pass
        raise
    return result
