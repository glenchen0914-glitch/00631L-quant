from src.assets import run_dual
from src.performance import update_dual_performance
from src.notify import main as notify_line

def main() -> None:
    run_dual()
    update_dual_performance()
    notify_line()

if __name__ == "__main__":
    main()
