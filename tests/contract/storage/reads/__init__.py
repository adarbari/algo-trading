"""Storage contract of the partition reads that pick a part of a partition or only count it:
one run's rows (read_run), each group's newest run (read_latest_runs), the stats of a partition
(partition_stats); every table backend passes it."""
