"""
AdaptiveThrottle (自動スロットル) の単体テスト (D-5)
"""
from src.crawler.webengine_crawler import AdaptiveThrottle


def test_adaptive_throttle_degrades_on_failures_and_recovers_on_streak():
    throttle = AdaptiveThrottle(
        base_max_tabs=4,
        base_interval_sec=0.2,
        window_size=10,
        fail_threshold=3,
        recovery_streak=20,
        max_interval_sec=2.0,
    )
    assert throttle.active_tabs == 4
    assert throttle.current_interval_sec == 0.2

    # 2回失敗ではまだ減速しない
    assert throttle.record_failure() is None
    assert throttle.record_failure() is None
    assert throttle.active_tabs == 4

    # 直近10件中3回目の失敗で1段階減速 (tabs: 4->3, interval: 0.2->0.4)
    msg = throttle.record_failure()
    assert msg is not None
    assert throttle.active_tabs == 3
    assert throttle.current_interval_sec == 0.4

    # さらに3回失敗すると2段階目減速 (tabs: 3->2, interval: 0.4->0.8)
    throttle.record_failure()
    throttle.record_failure()
    msg2 = throttle.record_failure()
    assert msg2 is not None
    assert throttle.active_tabs == 2
    assert throttle.current_interval_sec == 0.8

    # 19回連続成功ではまだ回復しない
    for _ in range(19):
        assert throttle.record_success() is None
    assert throttle.active_tabs == 2

    # 20回目の連続成功で1段階回復 (tabs: 2->3, interval: 0.8->0.4)
    rec_msg1 = throttle.record_success()
    assert rec_msg1 is not None
    assert throttle.active_tabs == 3
    assert throttle.current_interval_sec == 0.4

    # さらに20回連続成功で初期値へ完全回復 (tabs: 3->4, interval: 0.4->0.2)
    for _ in range(19):
        assert throttle.record_success() is None
    rec_msg2 = throttle.record_success()
    assert rec_msg2 is not None
    assert throttle.active_tabs == 4
    assert throttle.current_interval_sec == 0.2

