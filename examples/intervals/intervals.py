def merge_intervals(intervals):
    intervals.sort()
    merged = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start < merged[-1][1]:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return merged
