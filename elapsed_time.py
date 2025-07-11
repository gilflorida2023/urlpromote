import time

def format_duration(seconds):
    """
    Formats a duration in seconds into a human-readable string with appropriate units.
    - Sub-second durations: Shows three decimal places (e.g., "0.500s")
    - Whole seconds: Shows just seconds (e.g., "5s")
    - Minutes and up: Shows all relevant units, space-separated (e.g., "2m 30s", "1h 30m 45s")
    - Supports up to weeks for long-running operations
    """
    # Break down the duration into components
    weeks = int(seconds // (7 * 24 * 60 * 60))
    days = int((seconds % (7 * 24 * 60 * 60)) // (24 * 60 * 60))
    hours = int((seconds % (24 * 60 * 60)) // (60 * 60))
    minutes = int((seconds % (60 * 60)) // 60)
    secs = int(seconds % 60)
    milliseconds = int(round((seconds - int(seconds)) * 1000))

    def format_seconds(secs, ms):
        if secs == 0 and ms > 0:
            return f"0.{ms:03d}s"
        elif ms == 0:
            return f"{secs}s"
        else:
            return f"{secs}.{ms:03d}s"

    # Build the output according to the most significant non-zero unit
    parts = []
    if weeks > 0:
        parts.append(f"{weeks}w")
        parts.append(f"{days}d")
        parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        parts.append(format_seconds(secs, milliseconds))
    elif days > 0:
        parts.append(f"{days}d")
        parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        parts.append(format_seconds(secs, milliseconds))
    elif hours > 0:
        parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        parts.append(format_seconds(secs, milliseconds))
    elif minutes > 0:
        parts.append(f"{minutes}m")
        if secs > 0 or milliseconds > 0:
            parts.append(format_seconds(secs, milliseconds))
    else:
        parts.append(format_seconds(secs, milliseconds))
    return " ".join(parts)

def measure_elapsed_time(func, *args, **kwargs):
    """
    Measures the elapsed time of a function and returns a formatted string.
    Usage:
        def my_function(): ...
        elapsed = measure_elapsed_time(my_function)
        print(elapsed)
    Or with arguments:
        elapsed = measure_elapsed_time(some_func, arg1, arg2)
    """
    start = time.perf_counter()
    func(*args, **kwargs)
    end = time.perf_counter()
    duration = end - start
    return format_duration(duration)

# Example usage:
if __name__ == "__main__":
    import time

    def test_sleep():
        time.sleep(1.5)

    print(measure_elapsed_time(test_sleep))  # e.g. "1.500s"

    def long_sleep():
        time.sleep(125)

    print(measure_elapsed_time(long_sleep))  # e.g. "2m 5s"

    def week_sleep():
        time.sleep(0.01)  # simulate, don't actually sleep a week!
    # You can mock/replace time.perf_counter for actual tests
