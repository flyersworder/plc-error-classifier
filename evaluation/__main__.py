"""CLI entry point for evaluation package.

Usage:
    uv run python -m evaluation generate  # Generate test cases
    uv run python -m evaluation run       # Run evaluation
"""

import asyncio
import sys


def main():
    """Main entry point for the evaluation CLI."""
    if len(sys.argv) < 2:
        print("Usage: python -m evaluation <command>")
        print("Commands:")
        print("  generate  - Generate synthetic test cases")
        print("  run       - Run evaluation on test suite")
        sys.exit(1)

    command = sys.argv[1]

    if command == "generate":
        from .generator import main as generator_main

        asyncio.run(generator_main())
    elif command == "run":
        from .run_eval import main as eval_main

        test_suite_path = sys.argv[2] if len(sys.argv) > 2 else None
        asyncio.run(eval_main(test_suite_path))
    else:
        print(f"Unknown command: {command}")
        print("Use 'generate' or 'run'")
        sys.exit(1)


if __name__ == "__main__":
    main()
