import sys, logging, time
sys.path.insert(0, '/home/ec2-user/tiger-brain-v6')
logging.disable(logging.CRITICAL)
from data.tick_bars import TickBarAggregator
import inspect
print("=== data/tick_bars.py — REAL STRUCTURE ===")
print(inspect.getsource(TickBarAggregator))
