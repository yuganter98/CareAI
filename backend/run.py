import uvicorn

if __name__ == "__main__":
    # Start Uvicorn server automatically on port 8000 with hot-reload enabled
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
