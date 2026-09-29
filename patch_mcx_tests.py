p = '/home/ec2-user/tiger-brain-v6/tests/test_session_brain.py'
s = open(p).read()

old1 = '''    def test_force_hunt_mcx_2230_floor_60(self):
        # MCX: 22:30 with 0 MCX entries → floor 60
        h = HuntStatus(date="2026-09-04")
        force, threshold, reason = should_force_hunt(time(22, 30), h, "mcx")
        assert force is True
        assert threshold == 60.0
        assert "0 MCX entries" in reason

    def test_force_hunt_mcx_progressive_floor(self):
        # MCX: 22:30→60, 22:35→55 (min)
        h = HuntStatus(date="2026-09-04")
        assert should_force_hunt(time(22, 30), h, "mcx")[1] == 60.0
        assert should_force_hunt(time(22, 35), h, "mcx")[1] == 55.0
        assert should_force_hunt(time(23, 0), h, "mcx")[1] == 55.0  # floored at 55'''

new1 = '''    def test_force_hunt_mcx_immediate_floor_55(self):
        # MCX: immediate hunt — any MCX-live time with 0 entries → floor 55
        h = HuntStatus(date="2026-09-04")
        force, threshold, reason = should_force_hunt(time(22, 30), h, "mcx")
        assert force is True
        assert threshold == 55.0
        assert "0 MCX entries" in reason

    def test_force_hunt_mcx_fires_early_in_window(self):
        # Owner directive: 22:30 gating removed. Hunt must be live much
        # earlier in the MCX session, not only near close.
        h = HuntStatus(date="2026-09-04")
        for t in (time(9, 15), time(12, 0), time(15, 0),
                  time(19, 0), time(21, 0), time(22, 30), time(23, 0)):
            force, threshold, _ = should_force_hunt(t, h, "mcx")
            assert force is True, f"MCX hunt not active at {t}"
            assert threshold == 55.0, f"floor not 55 at {t}"

    def test_force_hunt_mcx_never_below_55(self):
        # Floor is pinned at 55 across the whole MCX window.
        h = HuntStatus(date="2026-09-04")
        for t in (time(9, 0), time(19, 0), time(23, 10)):
            assert should_force_hunt(t, h, "mcx")[1] >= 55.0

    def test_no_mcx_hunt_outside_mcx_hours(self):
        # Before 09:00 and after 23:15 MCX is closed → no hunt.
        h = HuntStatus(date="2026-09-04")
        assert should_force_hunt(time(8, 0), h, "mcx")[0] is False
        assert should_force_hunt(time(23, 30), h, "mcx")[0] is False'''

assert old1 in s, 'MCX tests not found'
s = s.replace(old1, new1, 1)
open(p, 'w').write(s)
print("TESTS updated for immediate MCX hunt")
