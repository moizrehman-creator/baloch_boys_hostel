# run_prod.py — production entry point
from waitress import serve
from app import app

if __name__ == "__main__":
    print("Serving Baloch Boys Hostel on http://0.0.0.0:5000")
    serve(
        app,
        host="0.0.0.0",
        port=5000,
        threads=8,
        ident="Baloch Boys Hostel",
        channel_timeout=60,
    )