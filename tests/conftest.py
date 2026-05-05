"""pytest 配置 — 把项目根加入 sys.path，使测试可以 `import voice_lab` 等顶层模块。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
