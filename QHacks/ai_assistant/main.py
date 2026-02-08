"""Entry point for the voice assistant."""

from core.controller import AssistantController
import traceback


def main():
    controller = AssistantController()
    try:
        controller.start()
    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
