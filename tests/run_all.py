"""逐模块子进程运行全部测试。

ok.test 的 TaskTestCase 依赖 Qt 单例：同一进程里 init_ok/destroy_ok 只能完成
一次（destroy 后 QApplication 无法重建），所以多个测试模块必须分进程跑。
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    modules = sorted(path.stem for path in (ROOT / 'tests').glob('test_*.py'))
    failed = []
    for module in modules:
        print(f'===== tests.{module}')
        code = subprocess.run(
            [sys.executable, '-m', 'unittest', f'tests.{module}', '-v'],
            cwd=ROOT,
        ).returncode
        if code != 0:
            failed.append(module)
    print('失败模块:', ', '.join(failed) if failed else '无')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
