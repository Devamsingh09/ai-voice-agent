#!/bin/bash
echo "🚀 Starting AI Voice Agent..."

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

echo "Waiting for backend..."
sleep 3

streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0

trap "kill $BACKEND_PID" EXIT