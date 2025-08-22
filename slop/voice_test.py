from slop.stitch import compute_durations_from_alignment


def test_compute_durations_from_alignment(alignment, scenes):
    durations = compute_durations_from_alignment(alignment, scenes)
    print(durations)
    # print partial sum of durations
    partial_sums = [sum(durations[:i]) for i in range(1, len(durations))]

    assert durations == [
        8.661,
        9.009,
        6.105999999999998,
        7.6739999999999995,
        6.722999999999999,
        7.744,
        7.813000000000002,
        7.743000000000002,
        8.150000000000006,
        7.313999999999993,
        9.21799999999999,
        7.697000000000003,
    ]
    assert partial_sums == [
        8.661,
        17.67,
        23.776,
        31.45,
        38.173,
        45.917,
        53.730000000000004,
        61.473000000000006,
        69.62300000000002,
        76.93700000000001,
        86.155,
    ]
