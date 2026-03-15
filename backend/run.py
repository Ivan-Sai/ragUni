"""
Convenience script to run the University Knowledge API server
"""
import os
import uvicorn

if __name__ == "__main__":
    is_dev = os.environ.get("ENV", "development").lower() == "development"
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=is_dev,
        log_level="info",
    )
