merge_intervals should accept a list of closed intervals [start, end], with start <= end,
and return sorted merged intervals. Overlapping intervals and intervals that touch at
an endpoint should merge. Empty input should return []. Nested intervals must not
shrink an already merged interval. Do not mutate the input list or its inner lists.
The current implementation crashes for empty input and gives incorrect results for
some touching/nested intervals. Preserve the merge_intervals(intervals) API.
