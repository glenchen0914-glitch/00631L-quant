from src.pipeline import run
from src.performance import update_performance
from src.publish_summary import main as publish_summary
from src.notify import main as notify_line

def main() -> None:
    run()
    update_performance()
    publish_summary()
    notify_line()

if __name__ == "__main__":
    main()
