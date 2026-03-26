"""CLI entry point for growth-api."""
import argparse


def main():
    parser = argparse.ArgumentParser(
        prog="growth-api",
        description="Start the Growth Tools REST API (website + GitHub auditor)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(
        "growth_tools.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
